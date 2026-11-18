---
id: US-3.4-T-2
story: US-3.4
sprint: 3
assignee: Samin Salman
estimate_hours: 4
---

# Play locally archived video in the archive viewer

## Description

Serves user story 3.4: users can view media from archived websites. This
task verifies and, if necessary, enables playback of a locally saved video
in the frontend's archive viewer. The video and HTML are already present in
the archive. Downloading media belongs to task 3.4.1 and is out of scope;
audio playback and streaming from remote sites are also out of scope.

## Specs

- `frontend/src/archive_viewer.py` provides `ArchiveViewer.open_archive`,
  which opens a local HTML file in the Qt WebEngine viewer.
- A test archive contains an HTML `video` element with controls and a
  relative path to a local video file in a format supported by the test
  environment's Qt WebEngine. The test runs without a network connection.
- After the archived HTML loads, the video can load its local source, begin
  playing, advance its playback time, and pause through the viewer.
- If the referenced video file is missing, the page remains usable and the
  video reports a media error rather than playing successfully.
- Automated frontend tests exercise the real `ArchiveViewer`, including
  playback state and time, using a small local video fixture.

## Requirements

- Keep archive viewing local; the test must not fetch media from the network.
- Preserve existing HTML viewing behavior and existing frontend tests.
- Do not modify archived HTML or media files during playback.
- Do not claim support for codecs that the installed Qt WebEngine cannot play.

## Acceptance criteria

1. Opening the test archive displays the page and loads its relative local
   video source without a network connection.
2. Starting the video advances its playback time from its initial position.
3. Pausing the video stops playback and leaves it in the paused state.
4. When the video file is missing, the video reports a media error and the
   surrounding archived page remains usable.
