import argparse
import logging
from pathlib import Path
import time
from typing import Set
import boto3
from botocore import UNSIGNED
from botocore.config import Config
import json
from datetime import datetime

# Configure logging 
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

import json
from datetime import datetime

# DOWNLOAD_DIR = Path('data/binance')
TRADING_TYPE = ['spot','um', 'cm']
ARCHIVE_TYPE = ['daily', 'monthly']
INTERVALS = ["1s", "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1mo"]
DAILY_INTERVALS = ["1s", "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"]


def get_prefix(trading_type, archive_type) -> str:
    if trading_type not in TRADING_TYPE:
        # logger.error(f"Trading type {trading_type} not supported")
        raise ValueError(f"Trading type {trading_type} not supported")

    if trading_type == 'spot':
        prefix = f'data/spot/{archive_type}/klines/'
    else:
        prefix = f'data/futures/{trading_type}/{archive_type}/klines/'
    return prefix

def get_trading_pairs(trading_type) -> Set[str]:
    """Get trading pairs using S3 delimiter and caching with pagination"""

    if not trading_type in TRADING_TYPE:
        logger.error(f"Trading type {trading_type} not supported")
        return set()
    
    try:
        s3 = boto3.client(
            's3',
            region_name='ap-northeast-1',
            config=Config(signature_version=UNSIGNED)
        )

        # Use paginator to handle >1000 items
        paginator = s3.get_paginator('list_objects_v2')
        pairs = set()
        
        prefix = get_prefix(trading_type, 'daily')

        for page in paginator.paginate(
            Bucket='data.binance.vision',
            Prefix=prefix,
            Delimiter='/'
        ):
            # Extract pairs from each page
            page_pairs = {
                prefix['Prefix'].split('/')[-2]
                for prefix in page.get('CommonPrefixes', [])
            }
            # for common_prefix in page.get('CommonPrefixes', []):
            #     print(common_prefix['Prefix'].split('/'))
            # exit()
            pairs.update(page_pairs)
            logger.debug(f"Found {len(page_pairs)} pairs on current page, total: {len(pairs)}")

        # Cache results
        cache_data = {
            'timestamp': datetime.now().isoformat(),
            'pairs': list(pairs)
        }

        logger.info(f"Found and cached {len(pairs)} trading pairs")
        return pairs

    except Exception as e:
        logger.error(f"Error accessing S3: {e}")
        return set()

def filter_usdt_pairs(pairs: Set[str]) -> Set[str]:
    """Filter pairs to only include USDT pairs"""
    usdt_pairs = {pair for pair in pairs if pair.endswith('USDT')}
    logger.info(f"Found {len(usdt_pairs)} USDT pairs")
    return usdt_pairs

def within_date_range(date: str, start_date: str, end_date: str) -> bool:
    """Check if date is within start_date and end_date"""
    date_obj = datetime.strptime(date, '%Y-%m-%d').date()
    start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
    end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
    return start_date_obj <= date_obj <= end_date_obj

def get_date_from_filename(file_name: str) -> str:
    """Extract date from filename (format: SYMBOL-interval-YYYY-MM-DD.zip) or
    (format: SYMBOL-interval-YYYY-MM.zip)
    """
    parts = file_name.split('-')
    if len(parts) == 5:
        # Format: SYMBOL-interval-YYYY-MM-DD.zip
        file_date_str = f"{parts[2]}-{parts[3]}-{parts[4].split('.')[0]}"
    elif len(parts) == 4:
        # Format: SYMBOL-interval-YYYY-MM.zip
        file_date_str = f"{parts[2]}-{parts[3].split('.')[0]}-01"
    else:
        raise ValueError(f"Unexpected file name format: {file_name}")
    
    return file_date_str


def download_klines(
    trading_type: str,
    archive_type: str,
    pair: str, 
    interval: str,
    start_date: str,  # Format: YYYY-MM-DD
    end_date: str,     # Format: YYYY-MM-DD
    download_dir: str
) -> bool:
    """Download kline data for specific pair and interval"""

    if trading_type not in TRADING_TYPE:
        logger.error(f"Trading type {trading_type} not supported")
        return False
    
    if archive_type not in ARCHIVE_TYPE:
        logger.error(f"Archive type {archive_type} not supported")
        return False

    if interval not in INTERVALS:
        logger.error(f"Interval {interval} not supported")
        return False
    
    if archive_type == 'daily' and interval not in DAILY_INTERVALS:
        logger.error(f"Interval {interval} not supported for daily archive")
        return False

    try:
        s3 = boto3.client(
            's3',
            region_name='ap-northeast-1',
            config=Config(signature_version=UNSIGNED)
        )

        # Create save directory
        download_dir_path = Path(download_dir)
        if trading_type == 'spot':
            save_dir = download_dir_path / trading_type / archive_type / pair / interval
        else:
            save_dir = download_dir_path / 'futures' / trading_type / archive_type / pair / interval
        save_dir.mkdir(parents=True, exist_ok=True)

        # List available files
        prefix = get_prefix(trading_type, archive_type) + f"{pair}/{interval}/"
        # prefix = f"data/spot/daily/klines/{pair}/{interval}/"
        paginator = s3.get_paginator('list_objects_v2')
        
        for page in paginator.paginate(Bucket='data.binance.vision', Prefix=prefix):

            if 'Contents' not in page:
                continue
                
            for obj in page['Contents']:
                file_name = obj['Key'].split('/')[-1]
                if not file_name.endswith('.zip'):
                    continue
                    
                if not within_date_range(get_date_from_filename(file_name), start_date, end_date):
                    continue

                # Download file
                save_path = save_dir / file_name
                if save_path.exists():
                    logger.info(f"File exists, skipping: {file_name}")
                    continue
                    
                logger.info(f"Downloading {file_name}")
                s3.download_file(
                    Bucket='data.binance.vision',
                    Key=obj['Key'],
                    Filename=str(save_path)
                )
                time.sleep(0.1)  # Rate limiting
                
        return True
        
    except Exception as e:
        logger.error(f"Error downloading {pair} {interval}: {e}")
        return False


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Download Binance historical data.')
    parser.add_argument('--trading_type', type=str, choices=['spot', 'um', 'cm'], default='spot', help='Trading type (default: spot)')
    parser.add_argument('--archive_type', type=str, choices=['daily', 'monthly'], default='monthly', help='Archive type (default: monthly)')
    parser.add_argument('--intervals', type=str, nargs='+', default=['1h'], help='List of intervals (default: ["1h"])')
    parser.add_argument('--start_date', type=str, required=True, help='Start date (format: YYYY-MM-DD)')
    parser.add_argument('--end_date', type=str, required=True, help='End date (format: YYYY-MM-DD)')
    # parser.add_argument('--pairs', type=str, nargs='+', required=True, help='List of trading pairs')
    parser.add_argument('--pairs', type=str, nargs='+', default=None, help='List of trading pairs (default: None)')
    parser.add_argument('--download_dir', type=str, default='data/binance', help='Directory to save downloaded data (default: data/binance)')
    return parser.parse_args()

def main():
    # Parse command line arguments
    args = parse_arguments()


    
    # Configuration from arguments
    trading_type = args.trading_type
    archive_type = args.archive_type
    intervals = args.intervals
    start_date = args.start_date
    end_date = args.end_date
    pairs = args.pairs
    download_dir = args.download_dir

    logger.info(f"download_dir: {download_dir}")

    # Create download directory
    Path(download_dir).mkdir(parents=True, exist_ok=True)

    if archive_type == 'monthly':
        start_date = start_date[:7] + '-01'
        end_date = end_date[:7] + '-01'

    if pairs is None or len(pairs) == 0:
        all_pairs = get_trading_pairs(trading_type)
        pairs = filter_usdt_pairs(all_pairs)
        # print(pairs, len(pairs))

    logger.info(f"Downloading {archive_type} data for {len(pairs)} pairs")
    logger.info(f"pairs: {pairs}")

    # Download data for each pair and interval
    for pair in pairs:
        for interval in intervals:
            download_klines(trading_type, archive_type, pair, interval, start_date, end_date, download_dir)


if __name__ == '__main__':
    main()
