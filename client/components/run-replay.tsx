"use client"

import {
  MediaControlBar,
  MediaController,
  MediaFullscreenButton,
  MediaPipButton,
  MediaPlaybackRateButton,
  MediaPlayButton,
  MediaSeekBackwardButton,
  MediaSeekForwardButton,
  MediaTimeDisplay,
  MediaTimeRange,
} from "media-chrome/react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { artifactUrl, type Run } from "@/lib/runs"

function formatBytes(bytes: number) {
  return `${(bytes / 1024).toFixed(bytes < 1024 * 100 ? 1 : 0)} KB`
}

export function RunReplay({ run }: { run: Run }) {
  const replay = run.artifacts.find((artifact) => artifact.kind === "video")
  if (!replay) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Replay</CardTitle>
        <CardDescription>
          Browser recording · {formatBytes(replay.size_bytes)}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <MediaController className="aspect-video w-full overflow-hidden bg-black">
          <video
            slot="media"
            src={artifactUrl(replay)}
            preload="metadata"
            playsInline
            aria-label="Browser run replay"
            className="size-full object-contain"
          />
          <MediaControlBar className="w-full">
            <MediaPlayButton />
            <MediaSeekBackwardButton />
            <MediaSeekForwardButton />
            <MediaTimeDisplay showDuration />
            <MediaTimeRange />
            <MediaPlaybackRateButton />
            <MediaPipButton />
            <MediaFullscreenButton />
          </MediaControlBar>
        </MediaController>
      </CardContent>
    </Card>
  )
}
