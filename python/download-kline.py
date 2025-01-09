#!/usr/bin/env python

"""
  script to download klines.
  set the absolute path destination folder for STORE_DIRECTORY, and run

  e.g. STORE_DIRECTORY=/data/ ./download-kline.py

"""
import sys
import os
import json
import http.client
from datetime import datetime
import pandas as pd
from enums import *
from utility import download_file, get_all_symbols, get_parser, get_start_end_date_objects, convert_to_date_object, \
  get_path


def load_progress(progress_file):
  try:
    with open(progress_file, 'r') as f:
      return json.load(f)
  except FileNotFoundError:
    return {}

def save_progress(progress_file, progress):
  with open(progress_file, 'w') as f:
    json.dump(progress, f)

def download_monthly_klines(trading_type, symbols, num_symbols, intervals, years, months, start_date, end_date, folder, checksum, force=False):
  current = 0
  date_range = None
  progress_file = os.path.join(folder or os.environ.get('STORE_DIRECTORY', '.'), 'download_progress.json')
  progress = load_progress(progress_file)

  if start_date and end_date:
    date_range = start_date + " " + end_date

  if not start_date:
    start_date = START_DATE
  else:
    start_date = convert_to_date_object(start_date)

  if not end_date:
    end_date = END_DATE
  else:
    end_date = convert_to_date_object(end_date)

  print("Found {} symbols".format(num_symbols))

  for symbol in symbols:
    if args.suffix and not symbol.endswith(args.suffix):
          continue
    print("[{}/{}] - start download monthly {} klines ".format(current+1, num_symbols, symbol))
    for interval in intervals:
      for year in years:
        for month in months:
          current_date = convert_to_date_object('{}-{}-01'.format(year, month))
          if current_date >= start_date and current_date <= end_date:
            path = get_path(trading_type, "klines", "monthly", symbol, interval)
            file_name = "{}-{}-{}-{}.zip".format(symbol.upper(), interval, year, '{:02d}'.format(month))
            
            # Check progress
            progress_key = f"{symbol}_{interval}_{year}_{month:02d}"
            if not force and progress.get(progress_key, False):
              print(f"Skipping already downloaded file: {file_name}")
              continue
            
            while True:
                try:
                    download_file(path, file_name, date_range, folder)
                    progress[progress_key] = True
                    save_progress(progress_file, progress)
                    break
                except http.client.RemoteDisconnected:
                    print(f"Connection lost while downloading {file_name}, retrying...")
                    continue

            if checksum == 1:
              checksum_path = get_path(trading_type, "klines", "monthly", symbol, interval)
              checksum_file_name = "{}-{}-{}-{}.zip.CHECKSUM".format(symbol.upper(), interval, year, '{:02d}'.format(month))
              while True:
                  try:
                      download_file(checksum_path, checksum_file_name, date_range, folder)
                      progress[f"{progress_key}_checksum"] = True
                      save_progress(progress_file, progress)
                      break
                  except http.client.RemoteDisconnected:
                      print(f"Connection lost while downloading {checksum_file_name}, retrying...")
                      continue

    current += 1

def download_daily_klines(trading_type, symbols, num_symbols, intervals, dates, start_date, end_date, folder, checksum, force=False):
  current = 0
  date_range = None
  progress_file = os.path.join(folder or os.environ.get('STORE_DIRECTORY', '.'), 'download_progress.json')
  progress = load_progress(progress_file)

  if start_date and end_date:
    date_range = start_date + " " + end_date

  if not start_date:
    start_date = START_DATE
  else:
    start_date = convert_to_date_object(start_date)

  if not end_date:
    end_date = END_DATE
  else:
    end_date = convert_to_date_object(end_date)

  #Get valid intervals for daily
  intervals = list(set(intervals) & set(DAILY_INTERVALS))
  print("Found {} symbols".format(num_symbols))

  for symbol in symbols:
    if args.suffix and not symbol.endswith(args.suffix):
          continue
    print("[{}/{}] - start download daily {} klines ".format(current+1, num_symbols, symbol))
    for interval in intervals:
      for date in dates:
        current_date = convert_to_date_object(date)
        if current_date >= start_date and current_date <= end_date:
          path = get_path(trading_type, "klines", "daily", symbol, interval)
          file_name = "{}-{}-{}.zip".format(symbol.upper(), interval, date)
          
          # Check progress
          progress_key = f"{symbol}_{interval}_{date}"
          if not force and progress.get(progress_key, False):
            print(f"Skipping already downloaded file: {file_name}")
            continue
          
          while True:
              try:
                  download_file(path, file_name, date_range, folder)
                  progress[progress_key] = True
                  save_progress(progress_file, progress)
                  break
              except http.client.RemoteDisconnected:
                  print(f"Connection lost while downloading {file_name}, retrying...")
                  continue

          if checksum == 1:
            checksum_path = get_path(trading_type, "klines", "daily", symbol, interval)
            checksum_file_name = "{}-{}-{}.zip.CHECKSUM".format(symbol.upper(), interval, date)
            while True:
                try:
                    download_file(checksum_path, checksum_file_name, date_range, folder)
                    progress[f"{progress_key}_checksum"] = True
                    save_progress(progress_file, progress)
                    break
                except http.client.RemoteDisconnected:
                    print(f"Connection lost while downloading {checksum_file_name}, retrying...")
                    continue

    current += 1

if __name__ == "__main__":
    parser = get_parser('klines')
    parser.add_argument('--suffix', help='Only process symbols with this suffix')
    parser.add_argument('--resume', action='store_true', help='Resume from last download progress')
    parser.add_argument('--force', action='store_true', help='Force re-download existing files')
    args = parser.parse_args(sys.argv[1:])

    if not args.symbols:
      print("fetching all symbols from exchange")
      symbols = get_all_symbols(args.type)
      num_symbols = len(symbols)
    else:
      symbols = args.symbols
      num_symbols = len(symbols)

    if args.dates:
      dates = args.dates
    else:
      period = convert_to_date_object(datetime.today().strftime('%Y-%m-%d')) - convert_to_date_object(
        PERIOD_START_DATE)
      dates = pd.date_range(end=datetime.today(), periods=period.days + 1).to_pydatetime().tolist()
      dates = [date.strftime("%Y-%m-%d") for date in dates]
      if args.skip_monthly == 0:
        download_monthly_klines(args.type, symbols, num_symbols, args.intervals, args.years, args.months, args.startDate, args.endDate, args.folder, args.checksum, args.force)
    if args.skip_daily == 0:
      download_daily_klines(args.type, symbols, num_symbols, args.intervals, dates, args.startDate, args.endDate, args.folder, args.checksum, args.force)

