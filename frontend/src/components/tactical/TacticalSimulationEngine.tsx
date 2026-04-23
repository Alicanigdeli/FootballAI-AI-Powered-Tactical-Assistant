"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import gsap from "gsap";
import { Pause, Play, RotateCcw, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { cn } from "@/lib/utils";

export type SimFrame = {
  timestamp: number;
  positions: Record<string, [number, number]>;
  ball?: [number, number];
  ball_owner?: string | null;
};

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

export function samplePositions(frames: SimFrame[], elapsedMs: number): Record<string, [number, number]> {
  if (!frames.length) return {};
  const sorted = [...frames].sort((a, b) => a.timestamp - b.timestamp);
  const t0 = sorted[0].timestamp;
  const t1 = sorted[sorted.length - 1].timestamp;
  const te = Math.min(Math.max(0, elapsedMs), t1 - t0);
  const absT = t0 + te;

  let i = 0;
  while (i < sorted.length - 1 && sorted[i + 1].timestamp < absT) i++;
  const f0 = sorted[i];
  const f1 = sorted[Math.min(i + 1, sorted.length - 1)];
  if (f0.timestamp === f1.timestamp) return { ...f0.positions };

  const u = (absT - f0.timestamp) / Math.max(f1.timestamp - f0.timestamp, 1e-6);
  const keys = new Set([...Object.keys(f0.positions), ...Object.keys(f1.positions)]);
  const out: Record<string, [number, number]> = {};
  keys.forEach((k) => {
    const a = f0.positions[k];
    const b = f1.positions[k];
    if (!a && !b) return;
    if (!a) out[k] = b!;
    else if (!b) out[k] = a;
    else out[k] = [lerp(a[0], b[0], u), lerp(a[1], b[1], u)];
  });
  return out;
}

function drawPitch(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  positions: Record<string, [number, number]>,
  ball?: [number, number]
) {
  const m = 28;
  const pw = w - 2 * m;
  const ph = h - 2 * m;
  ctx.clearRect(0, 0, w, h);

  const stripes = 14;
  for (let s = 0; s < stripes; s++) {
    ctx.fillStyle = s % 2 === 0 ? "#0a1f14" : "#0c2818";
    ctx.fillRect(m + (s * pw) / stripes, m, pw / stripes + 1, ph);
  }

  ctx.strokeStyle = "rgba(255,255,255,0.22)";
  ctx.lineWidth = 2;
  ctx.strokeRect(m, m, pw, ph);

  ctx.beginPath();
  ctx.moveTo(m + pw / 2, m);
  ctx.lineTo(m + pw / 2, m + ph);
  ctx.stroke();

  const r = Math.min(pw, ph) * 0.14;
  ctx.beginPath();
  ctx.arc(m + pw / 2, m + ph / 2, r, 0, Math.PI * 2);
  ctx.stroke();

  const boxW = pw * 0.18;
  const boxH = ph * 0.35;
  ctx.strokeRect(m, m + ph / 2 - boxH / 2, boxW, boxH);
  ctx.strokeRect(m + pw - boxW, m + ph / 2 - boxH / 2, boxW, boxH);

  Object.entries(positions).forEach(([id, [nx, ny]]) => {
    const px = m + nx * pw;
    const py = m + ny * ph;
    const hue = id.toLowerCase().startsWith("a") ? "#8b5cf6" : "#06b6d4";
    ctx.beginPath();
    ctx.fillStyle = hue;
    ctx.arc(px, py, 11, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.9)";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = "#fff";
    ctx.font = "600 8px system-ui,sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const label = id.length > 4 ? id.slice(0, 3) : id;
    ctx.fillText(label, px, py + 0.5);
  });

  if (ball && ball.length === 2) {
    const [bx, by] = ball;
    const px = m + bx * pw;
    const py = m + by * ph;
    ctx.beginPath();
    ctx.fillStyle = "rgba(255,255,255,0.95)";
    ctx.arc(px, py, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(0,0,0,0.55)";
    ctx.lineWidth = 2;
    ctx.stroke();
  }
}

type Props = {
  frames: SimFrame[];
  className?: string;
};

export function TacticalSimulationEngine({ frames, className }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const timelineRef = useRef<gsap.core.Timeline | null>(null);
  const stateRef = useRef({ t: 0 });
  const [progress, setProgress] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [recording, setRecording] = useState(false);

  const sorted = useMemo(
    () => [...frames].sort((a, b) => a.timestamp - b.timestamp),
    [frames]
  );

  const t0 = sorted[0]?.timestamp ?? 0;
  const t1 = sorted[sorted.length - 1]?.timestamp ?? 0;
  const totalMs = Math.max(t1 - t0, 1);

  const renderAt = useCallback(
    (elapsedMs: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const positions = samplePositions(sorted, elapsedMs);
      // Topu keyframe'lerden en yakın 2 frame arasında lineer örnekle (basit ama stabil).
      const sf = [...sorted].sort((a, b) => a.timestamp - b.timestamp);
      const t0 = sf[0]?.timestamp ?? 0;
      const t1 = sf[sf.length - 1]?.timestamp ?? 0;
      const te = Math.min(Math.max(0, elapsedMs), t1 - t0);
      const absT = t0 + te;
      let i = 0;
      while (i < sf.length - 1 && sf[i + 1].timestamp < absT) i++;
      const f0 = sf[i];
      const f1 = sf[Math.min(i + 1, sf.length - 1)];
      const b0 = f0?.ball;
      const b1 = f1?.ball;
      let ball: [number, number] | undefined = b0 ?? b1;
      if (b0 && b1 && f0.timestamp !== f1.timestamp) {
        const u = (absT - f0.timestamp) / Math.max(f1.timestamp - f0.timestamp, 1e-6);
        ball = [lerp(b0[0], b1[0], u), lerp(b0[1], b1[1], u)];
      }
      drawPitch(ctx, canvas.width, canvas.height, positions, ball);
    },
    [sorted]
  );

  const buildTimeline = useCallback(() => {
    timelineRef.current?.kill();
    stateRef.current.t = 0;
    const tl = gsap.timeline({
      paused: true,
      onUpdate: () => {
        renderAt(stateRef.current.t);
        setProgress(stateRef.current.t / totalMs);
      },
      onComplete: () => {
        setPlaying(false);
        setProgress(1);
      },
    });
    tl.to(stateRef.current, {
      t: totalMs,
      duration: totalMs / 1000,
      ease: "none",
    });
    timelineRef.current = tl;
    renderAt(0);
    setProgress(0);
  }, [renderAt, totalMs]);

  useEffect(() => {
    buildTimeline();
    return () => {
      timelineRef.current?.kill();
    };
  }, [buildTimeline]);

  const play = () => {
    const tl = timelineRef.current;
    if (!tl) return;
    setPlaying(true);
    tl.play();
  };

  const pause = () => {
    timelineRef.current?.pause();
    setPlaying(false);
  };

  const reset = () => {
    timelineRef.current?.pause();
    timelineRef.current?.progress(0);
    stateRef.current.t = 0;
    renderAt(0);
    setProgress(0);
    setPlaying(false);
  };

  const onSeek = (vals: number[]) => {
    const v = vals[0] ?? 0;
    const tl = timelineRef.current;
    if (!tl) return;
    tl.pause();
    setPlaying(false);
    tl.progress(v);
    stateRef.current.t = v * totalMs;
    renderAt(stateRef.current.t);
    setProgress(v);
  };

  if (!sorted.length) {
    return (
      <Card className={cn("border-[var(--border)] bg-[var(--card)]/80", className)}>
        <CardHeader>
          <CardTitle className="text-base text-cyan-400">Simülasyon Hazırlanıyor</CardTitle>
          <CardDescription className="text-xs">Uyumlu bir taktisel veri dizisi bekleniyor.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const exportWebm = async () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const stream = canvas.captureStream(30);
    const mime =
      MediaRecorder.isTypeSupported("video/webm;codecs=vp9") ?
        "video/webm;codecs=vp9"
      : "video/webm";

    const chunks: BlobPart[] = [];
    const rec = new MediaRecorder(stream, { mimeType: mime });
    rec.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };

    await new Promise<void>((resolve, reject) => {
      rec.onerror = () => reject(new Error("MediaRecorder error"));
      rec.onstop = () => resolve();
      rec.start(100);
      setRecording(true);
      reset();
      const tl = timelineRef.current;
      if (!tl) {
        rec.stop();
        setRecording(false);
        resolve();
        return;
      }
      tl.eventCallback("onComplete", null);
      tl.eventCallback("onComplete", () => {
        rec.stop();
        setRecording(false);
        setPlaying(false);
      });
      setPlaying(true);
      tl.play();
    });

    const blob = new Blob(chunks, { type: "video/webm" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `tactical-sim-${Date.now()}.webm`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card className={cn("border-[var(--border)] bg-[var(--card)]/80", className)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          Taktik simülasyon
        </CardTitle>
        <CardDescription className="text-xs">
          Animasyonu oynatarak veya zaman çizelgesini kaydırarak taktiksel dizilimi inceleyin.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="overflow-hidden rounded-lg border border-[var(--border)] bg-black/40 shadow-inner">
          <canvas
            ref={canvasRef}
            width={720}
            height={440}
            className="h-auto w-full max-w-full"
          />
        </div>

        <div className="space-y-2">
          <div className="flex justify-between text-xs text-[var(--muted-foreground)]">
            <span>Zaman çizgisi</span>
            <span>{Math.round(progress * totalMs)} ms / {totalMs} ms</span>
          </div>
          <Slider
            value={[progress]}
            min={0}
            max={1}
            step={0.001}
            onValueChange={onSeek}
            disabled={!sorted.length}
          />
        </div>

        <div className="flex flex-wrap gap-2">
          {!playing ?
            <Button type="button" size="sm" onClick={play} disabled={!sorted.length}>
              <Play className="h-4 w-4" /> Oynat
            </Button>
          : <Button type="button" size="sm" variant="secondary" onClick={pause}>
              <Pause className="h-4 w-4" /> Duraklat
            </Button>}
          <Button type="button" size="sm" variant="outline" onClick={reset}>
            <RotateCcw className="h-4 w-4" /> Sıfırla
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => void exportWebm()}
            disabled={recording || !sorted.length}
          >
            <Video className="h-4 w-4" />
            {recording ? "Kaydediliyor…" : "WebM indir"}
          </Button>
        </div>

        <p className="text-[10px] text-[var(--muted-foreground)] opacity-70">
          * Video kaydı tarayıcı üzerinde gerçek zamanlı olarak oluşturulur.
        </p>
      </CardContent>
    </Card>
  );
}

export const DEFAULT_SIM_FRAMES: SimFrame[] = [
  {
    timestamp: 0,
    ball: [0.35, 0.52],
    ball_owner: "h2",
    positions: {
      h1: [0.25, 0.5],
      h2: [0.35, 0.35],
      h3: [0.35, 0.65],
      a1: [0.75, 0.5],
      a2: [0.65, 0.4],
    },
  },
  {
    timestamp: 1500,
    ball: [0.45, 0.5],
    ball_owner: "h2",
    positions: {
      h1: [0.32, 0.48],
      h2: [0.42, 0.38],
      h3: [0.4, 0.62],
      a1: [0.68, 0.52],
      a2: [0.58, 0.45],
    },
  },
  {
    timestamp: 4000,
    ball: [0.55, 0.48],
    ball_owner: null,
    positions: {
      h1: [0.48, 0.5],
      h2: [0.5, 0.42],
      h3: [0.5, 0.58],
      a1: [0.55, 0.48],
      a2: [0.52, 0.5],
    },
  },
];
