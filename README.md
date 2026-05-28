# Vid_Editor

Automated video clipping and ad insertion tool.

This project takes a video URL as input, downloads the video, splits it into smaller clips, and appends a fixed advertisement clip after each segment automatically.

Perfect for:
- Content repurposing
- Shorts and Reels generation
- Video chunking
- Automated ad insertion workflows

## Features

- Download video directly from a URL
- Automatically split long videos into smaller clips
- Append an advertisement video after every clip
- Fully automated processing pipeline
- Batch clip generation
- Simple configurable timing system

## Example Workflow

Input:
- Full movie or video URL
- 10-second advertisement clip

Processing:
1. Download video
2. Split into 50-second clips
3. Add 10-second ad at the end of each clip
4. Export final processed clips

Output:

```bash
clip_1.mp4
clip_2.mp4
clip_3.mp4
```
