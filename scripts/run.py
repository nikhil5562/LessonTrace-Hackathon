"""Standalone loopback launcher. Explicit .env only; never search parent projects."""
from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8897)
    args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error('Choose a local port between 1024 and 65535.')
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=False)
    import uvicorn
    uvicorn.run('lessontrace_site.main:app',host='127.0.0.1',port=args.port,access_log=False)

if __name__=='__main__':main()
