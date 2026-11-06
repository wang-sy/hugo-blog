"""Compatibility entry point for the former full-sitemap submission command."""
import sys
from submit_search import main

if __name__ == '__main__':
    sys.argv[1:1] = ['--engine', 'baidu']
    sys.exit(main())
