# CSE115A-Webber
The repository for Webber, a local website archiver being developed for CSE115A.

## Run the desktop app

Use Python 3.14 or newer. From the project root:

```sh
make setup
make install-browser
make run-frontend
```

The normal app starts its own local backend and reads real archives from
`~/.webber`. Use **Save a page** to archive a full HTTP/HTTPS URL, search the
sidebar as you type, and select a snapshot to open its saved page or raw HTML.
For a separate test collection:

```sh
scripts/run-frontend.sh --data-dir /tmp/webber-test-archives
```

`make run-demo` opens the bundled sample UI. `make test-offscreen` runs the
regular tests; `make test-integration` captures a temporary local website and
checks that its saved HTML, styles and image remain viewable after the original
server stops. See [frontend integration](docs/FRONTEND_INTEGRATION.md) for the
architecture, task boundaries and additional run options.


# Project Description (copied from GrepThink2)

## Problem Statement
Though powerful and expansive, web-based internet archival initiatives like the Internet Archive's Wayback Machine can also be fragile in their own ways: server instability, rate limits, takedowns by individuals and copyright holders, attacks from malicious actors, and the legal scrutiny that comes with maintaining a public-facing database can all compromise the integrity and future of such an archive. In the case of smaller archival sites, long term storage cannot be guaranteed, nor can the security of the data itself, in the case of sites such as archive.today. Any given user cannot necessarily be sure that they data they chose to archive will still be there the next day.

With that in mind, the purpose of this project is to provide a local desktop-based web archival alternative that gives the user ownership and relative security over the data they choose to archive.

## Project Goals
The main goals of the project are to develop a functioning program that handles both scraping and viewing, with the following functionality:

- Users should be able to pass URLs to the program, which will use an integrated web crawler that can scrape and parse data for archival
- Users should be able to view their archived data as a web page, using a limited web browser that displays the data
- Users should be able to view a list of web pages that they've archived inside the program

### Some extended goals:

- Calendar-based organization and browsing, like the Wayback Machine
- Hyperlink functionality, allowing users to follow links to other archived pages within the browser

### Some pie-in-the-sky goals:

- Recursive scraping: ability to recursively scrape a website by following all internal links
- Batch scraping: ability to scrape multiple sites at once
- Tab view: ability to view multiple archived pages at once
- Bookmarking specific archived sites
- Archive export for backup purposes


## Scope of Work
The project will involve developing a desktop program that should be able to supply a web crawler and a limited browser with support for HTML. It'll also involve developing a database. Being able to support JavaScript heavy or more complex sites would be nice as well, but that's very much a stretch goal.

## Tech Stack
Python, PySide6 / Qt Widgets and Qt WebEngine, a local Flask / Waitress backend,
Playwright for capture, and SQLite for archive metadata.
