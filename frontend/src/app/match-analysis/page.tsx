"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Loader2, Play, ExternalLink, Send, Trash2 } from "lucide-react";
import Link from "next/link";
import {
  matchAnalysesApi,
  postCoachMatchChat,
  postHeadCoach,
  postCoachDefense,
  postCoachOffense,
  postCoachSetPiece,
  postCoachPositioning,
  restApi,
  type Player,
} from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { TeamSelect } from "@/components/TeamSelect";
import { MatchSelect } from "@/components/MatchSelect";

type Override = { rating?: string; minutes?: string; position?: string };

export default function MatchAnalysisPage() {
  const queryClient = useQueryClient();
  const [homeId, setHomeId] = useState("");
  const [awayId, setAwayId] = useState("");
  const [mySide, setMySide] = useState<"home" | "away">("home");
  const [matchId, setMatchId] = useState("0");
  const [matchDate, setMatchDate] = useState("");
  const [coachInstruction, setCoachInstruction] = useState("");
  const [overrides, setOverrides] = useState<Record<number, Override>>({});

  const [coachSessionId, setCoachSessionId] = useState("");

  useEffect(() => {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
      setCoachSessionId(crypto.randomUUID());
    } else {
      setCoachSessionId(`sess-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`);
    }
  }, []);

  const [chatInput, setChatInput] = useState("");
  const [chatLog, setChatLog] = useState<{ role: string; content: string }[]>([]);

  const teamsQ = useQuery({
    queryKey: ["teams", "all-ma"],
    queryFn: () => restApi.teams({ page: 1, page_size: 100 }),
  });


  const [analysisType, setAnalysisType] = useState<"head" | "defense" | "offense" | "setpiece" | "positioning">("head");

  const homeTeamName = useMemo(() => {
    const id = Number(homeId);
    if (!id) return null;
    return teamsQ.data?.items?.find((t) => t.id === id)?.name ?? null;
  }, [teamsQ.data, homeId]);

  const awayTeamName = useMemo(() => {
    const id = Number(awayId);
    if (!id) return null;
    return teamsQ.data?.items?.find((t) => t.id === id)?.name ?? null;
  }, [teamsQ.data, awayId]);

  const homePlayersQ = useQuery({
    queryKey: ["players", "home", homeId],
    queryFn: () => restApi.players(Number(homeId)),
    enabled: homeId !== "" && !Number.isNaN(Number(homeId)),
  });

  const awayPlayersQ = useQuery({
    queryKey: ["players", "away", awayId],
    queryFn: () => restApi.players(Number(awayId)),
    enabled: awayId !== "" && !Number.isNaN(Number(awayId)),
  });

  const analysisNotes = useMemo(() => {
    const enrich = (list: Player[]) =>
      list.map((p) => {
        const o = overrides[p.id];
        if (!o || (!o.rating && !o.minutes && !o.position)) return null;
        return {
          id: p.id,
          name: `${p.firstname ?? ""} ${p.lastname ?? ""}`.trim(),
          team_id: p.team_id,
          patch: o,
        };
      }).filter(Boolean);

    const h = enrich(homePlayersQ.data ?? []);
    const a = enrich(awayPlayersQ.data ?? []);
    if (!h.length && !a.length) return "";
    return (
      "Oyuncu paneli düzenlemeleri (DB’ye yazılmadan LLM bağlamı):\n" +
      JSON.stringify({ home_team_id: Number(homeId) || null, home: h, away_team_id: Number(awayId) || null, away: a }, null, 2)
    );
  }, [homePlayersQ.data, awayPlayersQ.data, overrides, homeId, awayId]);

  const saveStats = useMutation({
    mutationFn: async () => {
      const tasks: Promise<unknown>[] = [];
      const apply = (list: Player[]) => {
        list.forEach((p) => {
          const o = overrides[p.id];
          if (!o) return;
          const games: Record<string, unknown> = {};
          if (o.rating) games.rating = Number(o.rating);
          if (o.minutes) games.minutes = Number(o.minutes);
          if (Object.keys(games).length)
            tasks.push(restApi.patchPlayerStats(p.id, { games }));
          if (o.position)
            tasks.push(restApi.patchPlayer(p.id, { position: o.position }));
        });
      };
      apply(homePlayersQ.data ?? []);
      apply(awayPlayersQ.data ?? []);
      if (!tasks.length) throw new Error("Kaydedilecek alan yok");
      await Promise.all(tasks);
    },
    onSuccess: () => {
      toast.success("Oyuncu istatistikleri veritabanına yazıldı");
      void homePlayersQ.refetch();
      void awayPlayersQ.refetch();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const [lastResult, setLastResult] = useState<string | null>(null);

  const runAnalysis = useMutation({
    mutationFn: async () => {
      const h = Number(homeId);
      const a = Number(awayId);
      if (!h || !a) throw new Error("Ev ve deplasman takım ID zorunlu");
      const payload = {
        match_id: Number(matchId) || 0,
        home_id: h,
        away_id: a,
        my_team_id: mySide === "home" ? h : a,
        match_date: matchDate || null,
        session_id: coachSessionId,
        coach_instruction: coachInstruction || null,
        analysis_notes: analysisNotes || null,
      };

      switch(analysisType) {
        case "defense": return postCoachDefense(payload);
        case "offense": return postCoachOffense(payload);
        case "setpiece": return postCoachSetPiece(payload);
        case "positioning": return postCoachPositioning(payload);
        case "head":
        default:
          return postHeadCoach(payload);
      }
    },
    onSuccess: (res) => {
      toast.success("Analiz tamamlandı");
      setLastResult(
        typeof res.result === "string" ? res.result : JSON.stringify(res.result, null, 2)
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const chatMutation = useMutation({
    mutationFn: async (msg: string) => {
      const data = await postCoachMatchChat(coachSessionId, msg);
      return { ...data, userMsg: msg };
    },
    onSuccess: (data) => {
      setChatLog((prev) => [
        ...prev,
        { role: "user", content: data.userMsg },
        { role: "assistant", content: data.reply },
      ]);
      setChatInput("");
      toast.success("Yanıt alındı");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Maç analizi</h1>
          <p className="text-sm text-[var(--muted-foreground)]">
            Takım yöneticisi olarak rakip ve ev sahibi takımı seçin, taktik talimatlarınızı girin ve analiz başlatın.
          </p>
        </div>
        <Link href="/match-analysis/history">
          <Button variant="outline" size="sm">Geçmiş Analizler</Button>
        </Link>
      </div>

      <Card className="border-[var(--border)] bg-[var(--card)]">
        <CardHeader>
          <CardTitle className="text-base">Maç parametreleri</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Ev sahibi takım</Label>
            <TeamSelect 
              value={homeId} 
              onChange={setHomeId} 
              placeholder="Ev sahibi seçin"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Deplasman takım</Label>
            <TeamSelect 
              value={awayId} 
              onChange={setAwayId} 
              placeholder="Deplasman seçin" 
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Maç tarihi (opsiyonel)</Label>
            <Input
              value={matchDate}
              onChange={(e) => setMatchDate(e.target.value)}
              placeholder="2026-04-09 20:00"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Bizim takım</Label>
            <div className="flex gap-2 pt-1">
              <Button
                type="button"
                size="sm"
                variant={mySide === "home" ? "default" : "outline"}
                onClick={() => setMySide("home")}
                className="flex-1"
              >
                {homeTeamName || "Ev"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant={mySide === "away" ? "default" : "outline"}
                onClick={() => setMySide("away")}
                className="flex-1"
              >
                {awayTeamName || "Dep"}
              </Button>
            </div>
          </div>
          <div className="md:col-span-2 lg:col-span-4 space-y-1.5">
            <Label className="text-xs">Teknik direktör notu</Label>
            <Textarea
              value={coachInstruction}
              onChange={(e) => setCoachInstruction(e.target.value)}
              placeholder="Örn: duran toplara ağırlık, rakip orta saha zayıf..."
              className="min-h-[80px]"
            />
          </div>
        </CardContent>
      </Card>



      <div className="grid gap-4 lg:grid-cols-2">
        <TeamColumn
          title="Ev sahibi"
          teamId={homeId}
          players={homePlayersQ.data ?? []}
          loading={homePlayersQ.isFetching}
          overrides={overrides}
          setOverrides={setOverrides}
        />
        <TeamColumn
          title="Deplasman"
          teamId={awayId}
          players={awayPlayersQ.data ?? []}
          loading={awayPlayersQ.isFetching}
          overrides={overrides}
          setOverrides={setOverrides}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          disabled={saveStats.isPending}
          onClick={() => saveStats.mutate()}
        >
          {saveStats.isPending ?
            <Loader2 className="h-4 w-4 animate-spin" />
          : null}
          Verileri Kaydet
        </Button>
        <div className="flex items-center gap-2 border-[var(--border)] rounded-md">
          <select
            value={analysisType}
            onChange={(e) => setAnalysisType(e.target.value as any)}
            className="h-9 rounded-md border border-[var(--border)] bg-[var(--input-bg)] px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring text-white"
          >
            <option value="head">Tüm Analiz (1 dk. sürebilir)</option>
            <option value="defense">Sadece Savunma</option>
            <option value="offense">Sadece Hücum</option>
            <option value="setpiece">Sadece Duran Top</option>
            <option value="positioning">Sadece Pozisyon</option>
          </select>
          <Button disabled={runAnalysis.isPending} onClick={() => runAnalysis.mutate()}>
            {runAnalysis.isPending ?
              <Loader2 className="h-4 w-4 animate-spin" />
            : <Play className="h-4 w-4" />}
            Analizi başlat
          </Button>
        </div>
      </div>

      {teamsQ.data && teamsQ.data.items.length > 0 && (
        <Card className="border-[var(--border)] bg-[var(--card)]/60">
          <CardHeader className="py-3">
            <CardTitle className="text-sm">Takım ID referansı (ilk 40)</CardTitle>
            <CardDescription className="text-xs">Veri sekmesinden tam liste.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {teamsQ.data.items.slice(0, 40).map((t) => (
              <Badge key={t.id} variant="outline" className="font-mono text-[10px]">
                {t.id}: {t.name}
              </Badge>
            ))}
          </CardContent>
        </Card>
      )}

      {lastResult && (
        <>
          <Separator />

          <Card className="border-[var(--border)]/60 bg-[var(--card)]/40">
            <CardContent className="flex items-center gap-3 py-4">
              <div className="flex-1 text-sm text-[var(--muted-foreground)]">
                Analiz tamamlandı. Taktik simülasyonlarını ayrı sayfadan oluşturabilirsiniz.
              </div>
              <Link href={`/simulation?match_id=${matchId}`}>
                <Button variant="secondary" size="sm">
                  <ExternalLink className="h-3.5 w-3.5 mr-1" />
                  Simülasyonlar
                </Button>
              </Link>
            </CardContent>
          </Card>

          <Card className="border-[var(--border)] bg-[#060d18]">
            <CardHeader>
              <CardTitle className="text-base">Taktik Analiz Raporu</CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[360px] w-full rounded-md border border-[var(--border)] p-4">
                <pre className="whitespace-pre-wrap text-xs text-cyan-100/90">{lastResult}</pre>
              </ScrollArea>
            </CardContent>
          </Card>

          <Card className="border-[var(--border)] bg-[var(--card)]">
            <CardHeader>
              <CardTitle className="text-base">Maç sohbeti</CardTitle>
              <CardDescription className="text-xs">
                Analiz sonrası aynı maç için takip soruları sorabilirsiniz.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {chatLog.length > 0 && (
                <ScrollArea className="h-[200px] w-full rounded-md border border-[var(--border)] p-3">
                  <div className="space-y-2 text-xs">
                    {chatLog.map((m, i) => (
                      <div
                        key={i}
                        className={
                          m.role === "user" ?
                            "rounded-md bg-sky-950/40 p-2 text-sky-100"
                          : "rounded-md bg-violet-950/30 p-2 text-violet-100"
                        }
                      >
                        <span className="font-semibold text-[10px] uppercase opacity-70">
                          {m.role === "user" ? "Siz" : "Asistan"}
                        </span>
                        <p className="whitespace-pre-wrap mt-1">{m.content}</p>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
              <div className="flex gap-2">
                <Textarea
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder="Örn: Duran top baskısını bir tık artıralım mı?"
                  className="min-h-[72px] text-sm"
                  disabled={chatMutation.isPending}
                />
                <Button
                  type="button"
                  className="shrink-0 self-end"
                  disabled={chatMutation.isPending || !chatInput.trim()}
                  onClick={() => chatMutation.mutate(chatInput.trim())}
                >
                  {chatMutation.isPending ?
                    <Loader2 className="h-4 w-4 animate-spin" />
                  : <Send className="h-4 w-4" />}
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function TeamColumn({
  title,
  teamId,
  players,
  loading,
  overrides,
  setOverrides,
}: {
  title: string;
  teamId: string;
  players: Player[];
  loading: boolean;
  overrides: Record<number, Override>;
  setOverrides: React.Dispatch<React.SetStateAction<Record<number, Override>>>;
}) {
  const update = (id: number, key: keyof Override, value: string) => {
    setOverrides((prev) => ({
      ...prev,
      [id]: { ...prev[id], [key]: value },
    }));
  };

  return (
    <Card className="border-[var(--border)] bg-gradient-to-b from-[var(--card)] to-[#060d18]">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription className="text-xs">
          {players.length > 0 ? `${players.length} oyuncu` : "Kadro yükleniyor..."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[420px] w-full rounded-md border border-[var(--border)]">
          <div className="space-y-2 p-2">
            {loading && (
              <p className="text-xs text-[var(--muted-foreground)]">Yükleniyor…</p>
            )}
            {!loading && !players.length && (
              <p className="text-xs text-[var(--muted-foreground)]">Takım ID girin veya veri çekin.</p>
            )}
            {players.map((p) => {
              const g = (p.games || {}) as Record<string, unknown>;
              const o = overrides[p.id];
              const posVal = o?.position ?? (p.position ?? "");
              const ratingVal =
                o?.rating ?? (g.rating != null ? String(g.rating) : "");
              const minVal =
                o?.minutes ?? (g.minutes != null ? String(g.minutes) : "");
              return (
                <div
                  key={p.id}
                  className="rounded-lg border border-[var(--border)] bg-black/20 p-3 text-xs"
                >
                  <div className="mb-2 font-medium text-cyan-200">
                    {p.firstname} {p.lastname}{" "}
                    <span className="text-[var(--muted-foreground)]">#{p.id}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <div>
                      <Label className="text-[10px] text-[var(--muted-foreground)]">Poz</Label>
                      <Input
                        className="h-8 text-xs"
                        value={posVal}
                        onChange={(e) => update(p.id, "position", e.target.value)}
                      />
                    </div>
                    <div>
                      <Label className="text-[10px] text-[var(--muted-foreground)]">Rating</Label>
                      <Input
                        className="h-8 text-xs"
                        value={ratingVal}
                        onChange={(e) => update(p.id, "rating", e.target.value)}
                      />
                    </div>
                    <div>
                      <Label className="text-[10px] text-[var(--muted-foreground)]">Dk</Label>
                      <Input
                        className="h-8 text-xs"
                        value={minVal}
                        onChange={(e) => update(p.id, "minutes", e.target.value)}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
