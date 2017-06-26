Print your stuff with a Python script instead of a web interface.

```
usage: utprint.py [-h] [-m] [-d] [-p {1,2}] [-c COPIES] [-r RANGE]
                  document [document ...]

Upload documents to UT's Library Print System.

positional arguments:
  document              a file (PDF, image, MS Office...) to print

optional arguments:
  -h, --help            show this help message and exit
  -m, --mono            print without color (save money)
  -d, --duplex          print double sided (duplex)
  -p {1,2}, --pages {1,2}
                        print two pages on each side of paper
  -c COPIES, --copies COPIES
                        print multiple copies
  -r RANGE, --range RANGE
                        print a specific set of pages (e.g. '1-5, 8, 11-13')
```

License: MIT.
