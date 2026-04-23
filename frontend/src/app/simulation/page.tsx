"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ChevronRight, Loader2, RefreshCw, Search, Trash2, Sparkles, ChevronDown } from "lucide-react";
import {
  TacticalSimulationEngine,
  DEFAULT_SIM_FRAMES,
  type SimFrame,
} from "@/components/tactical/TacticalSimulationEngine";
import {
  matchAnalysesApi,
  simulationsApi,
  postGenerateSimulations,
  type SimulationMeta,
  type SimulationDetail,
  postGenerateCustomSimulations,
} from "@/lib/api-client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { TeamSelect } from "@/components/TeamSelect";
import { MatchSelect } from "@/components/MatchSelect";
import { cn } from "@/lib/utils";

const SIM_TYPE_LABELS: Record<string, string> = {
  attack_organization: "Hücum Organizasyonu",
  defense_organization: "Savunma Organizasyonu",
  counter_attack: "Kontra Atak",
  set_piece_attack: "Duran Top Hücum",
  set_piece_defense: "Duran Top Savunma",
};

function SimTypeColor(simType: string) {
  const map: Record<string, string> = {
    attack_organization: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
    defense_organization: "bg-sky-500/20 text-sky-300 border-sky-500/30",
    counter_attack: "bg-amber-500/20 text-amber-300 border-amber-500/30",
    set_piece_attack: "bg-violet-500/20 text-violet-300 border-violet-500/30",
    set_piece_defense: "bg-rose-500/20 text-rose-300 border-rose-500/30",
  };
  return map[simType] ?? "bg-zinc-500/20 text-zinc-300 border-zinc-500/30";
}

function SimCard({
  meta,
  onDelete,
}: {
  meta: SimulationMeta;
  onDelete: (id: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const detailQ = useQuery({
    queryKey: ["simulation", meta.id],
    queryFn: () => simulationsApi.get(meta.id),
    enabled: open,
  });

  return (
    <Card className="border-[var(--border)] bg-black/30 overflow-hidden">
      <CardHeader 
        className="py-3 px-4 flex flex-row items-center justify-between cursor-pointer hover:bg-white/5 transition"
        onClick={() => setOpen(!open)}
      >
        <div className="flex items-center gap-3">
          <Badge className={SimTypeColor(meta.sim_type)} variant="outline">
            {SIM_TYPE_LABELS[meta.sim_type] ?? meta.sim_type}
          </Badge>
          <span className="text-sm font-medium text-white">{meta.title || "Adsız Simülasyon"}</span>
        </div>
        <div className="flex items-center gap-2">
           <Button
             variant="ghost"
             size="icon"
             className="h-8 w-8 text-red-400 hover:text-red-300 hover:bg-red-400/10"
             onClick={(e) => {
               e.stopPropagation();
               onDelete(meta.id);
             }}
           >
             <Trash2 className="h-4 w-4" />
           </Button>
           <ChevronRight className={`h-4 w-4 transition-transform ${open ? 'rotate-90' : ''}`} />
        </div>
      </CardHeader>

      {open && (
        <CardContent className="p-4 pt-2 space-y-4 border-t border-[var(--border)]">
          {meta.description && (
            <p className="text-xs text-[var(--muted-foreground)] italic px-1">
              {meta.description}
            </p>
          )}
          
          {detailQ.isLoading ? (
            <div className="flex h-40 items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          ) : detailQ.data ? (
            <TacticalSimulationEngine frames={detailQ.data.frames} />
          ) : (
            <div className="p-4 text-center text-xs text-red-400">Yükleme hatası.</div>
          )}
        </CardContent>
      )}
    </Card>
  );
}

function MatchAnalysisItem({ 
    analysis 
}: { 
    analysis: any 
}) {
    const [isExpanded, setIsExpanded] = useState(false);
    const [showAnalysis, setShowAnalysis] = useState(false);
    const queryClient = useQueryClient();

    const simsQ = useQuery({
        queryKey: ["simulations", analysis.match_id],
        queryFn: () => simulationsApi.list(analysis.match_id),
        enabled: isExpanded,
    });

    const handleDelete = async (simId: number) => {
        try {
            await simulationsApi.delete(simId);
            toast.success("Simülasyon silindi");
            queryClient.invalidateQueries({ queryKey: ["simulations", analysis.match_id] });
        } catch (e: unknown) {
            toast.error(e instanceof Error ? e.message : "Silme başarısız");
        }
    };

    return (
        <Card className={cn(
            "border-[var(--border)] bg-[var(--card)]/50 transition-all",
            isExpanded ? "ring-1 ring-cyan-500/30 bg-[var(--card)]/80" : "hover:bg-white/5"
        )}>
            <div 
                className="flex items-center justify-between p-4 cursor-pointer"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div className="flex items-center gap-4">
                    <div className="flex flex-col">
                        <span className="text-xs font-mono text-[var(--muted-foreground)]">#{analysis.match_id}</span>
                        <span className="text-sm font-semibold text-white">
                            {analysis.home_name} vs {analysis.away_name}
                        </span>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <Badge variant="secondary" className="text-[10px] opacity-70">
                        {analysis.match_date || "N/A"}
                    </Badge>
                    <ChevronDown className={cn("h-4 w-4 transition-transform", isExpanded && "rotate-180")} />
                </div>
            </div>

            {isExpanded && (
                <div className="border-t border-[var(--border)] p-4 space-y-4 animate-in fade-in duration-300">
                    <div className="space-y-2">
                        <Button 
                            variant="ghost" 
                            size="sm" 
                            className="text-xs text-cyan-400 hover:bg-cyan-400/10 h-8 gap-1.5"
                            onClick={() => setShowAnalysis(!showAnalysis)}
                        >
                            <Sparkles className="h-3.5 w-3.5" />
                            {showAnalysis ? "Raporu Gizle" : "Analiz Raporunu Gör"}
                        </Button>

                        {showAnalysis && (
                            <ScrollArea className="h-40 w-full rounded-md border border-[var(--border)] bg-black/40 p-3">
                                <pre className="whitespace-pre-wrap text-[11px] text-cyan-50/70 font-sans leading-relaxed">
                                    {analysis.result_text || "Analiz raporu yüklenemedi."}
                                </pre>
                            </ScrollArea>
                        )}
                    </div>

                    <div className="space-y-3">
                        <h4 className="text-[10px] uppercase tracking-wider font-bold text-[var(--muted-foreground)]">Simülasyonlar</h4>
                        {simsQ.isLoading ? (
                            <div className="flex items-center gap-2 text-xs py-4">
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                Yükleniyor...
                            </div>
                        ) : !simsQ.data?.length ? (
                            <div className="text-xs text-[var(--muted-foreground)] py-4">
                                Henüz simülasyon üretilmemiş.
                            </div>
                        ) : (
                            <div className="grid gap-3">
                                {simsQ.data.map((sim: any) => (
                                    <SimCard key={sim.id} meta={sim} onDelete={handleDelete} />
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </Card>
    );
}

function MatchSimulationsList() {
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;

  const analysesQ = useQuery({
    queryKey: ["match-analyses-list", page],
    queryFn: () => matchAnalysesApi.list({ page, page_size: PAGE_SIZE }),
  });

  const totalPages = analysesQ.data?.total ? Math.ceil(analysesQ.data.total / PAGE_SIZE) : 1;

  if (analysesQ.isLoading) {
    return (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-cyan-500" />
            <p className="text-sm text-[var(--muted-foreground)] italic">Maç listesi yükleniyor...</p>
        </div>
    );
  }

  const items = analysesQ.data?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
         <h3 className="text-sm font-medium text-[var(--muted-foreground)]">
            Analiz Edilen Maçlar ({analysesQ.data?.total ?? 0})
         </h3>
         <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => analysesQ.refetch()}
            className="h-8 text-xs gap-1.5"
         >
            <RefreshCw className={cn("h-3.5 w-3.5", analysesQ.isFetching && "animate-spin")} />
            Yenile
         </Button>
      </div>

      <div className="grid gap-4">
        {items.length === 0 ? (
            <Card className="border-dashed border-[var(--border)] bg-transparent py-10">
                <CardContent className="text-center space-y-2">
                    <p className="text-sm text-[var(--muted-foreground)]">Henüz hiç analiz yapılmamış.</p>
                </CardContent>
            </Card>
        ) : (
            items.map((m: any) => (
                <MatchAnalysisItem key={m.id} analysis={m} />
            ))
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex justify-center gap-2 pt-4">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            Önceki
          </Button>
          <div className="flex items-center px-4 text-xs text-white">
            Sayfa {page} / {totalPages}
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            Sonraki
          </Button>
        </div>
      )}
    </div>
  );
}

function SpecialAIProduction() {
    const [hId, setHId] = useState("");
    const [aId, setAId] = useState("");
    const [myId, setMyId] = useState("");
    const [matchId, setMatchId] = useState("");
    const [simType, setSimType] = useState("attack_organization");
    const [count, setCount] = useState(1);
    const [coachInstruction, setCoachInstruction] = useState("");
    const [loading, setLoading] = useState(false);
    const queryClient = useQueryClient();

    const handleGenerate = async () => {
        if (!hId || !aId) {
            toast.error("Lütfen ev sahibi ve deplasman takımlarını seçin");
            return;
        }
        // Match ID'yi backend'de belirleyeceksek 0 veya -1 gibi bir şey de atabiliriz
        const mId = Number(matchId) || 0; 
        setLoading(true);
        try {
            await postGenerateCustomSimulations(mId, {
                home_id: Number(hId),
                away_id: Number(aId),
                my_team_id: Number(myId) || Number(hId),
                sim_type: simType,
                count: count,
                coach_instruction: coachInstruction
            });
            toast.success(`Üretim başlatıldı. Birazdan listede görünecektir.`);
            // Listeyi yenilemesi için biraz bekleyebiliriz veya polllayabiliriz
            setTimeout(() => {
                queryClient.invalidateQueries({ queryKey: ["match-analyses-list"] });
            }, 2000);
        } catch (e: any) {
            toast.error(e.message || "Hata oluştu");
        } finally {
            setLoading(false);
        }
    };

    return (
        <Card className="border-[var(--border)] bg-[var(--card)]">
            <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-cyan-400" />
                    Özel Yapay Zeka Üretimi
                </CardTitle>
                <CardDescription className="text-xs">
                    Takımları seçin ve yapay zekanın sizin için taktiksel animasyonlar üretmesini sağlayın.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                <div className="grid gap-6 md:grid-cols-2">
                    <div className="space-y-4">
                        <div className="space-y-1.5">
                            <Label className="text-xs">Ev Sahibi Takım</Label>
                            <TeamSelect value={hId} onChange={setHId} />
                        </div>
                        <div className="space-y-1.5">
                            <Label className="text-xs">Deplasman Takımı</Label>
                            <TeamSelect value={aId} onChange={setAId} />
                        </div>
                        <div className="space-y-1.5">
                            <Label className="text-xs">Bizim Takım (h1-h11 olacak)</Label>
                            <TeamSelect value={myId} onChange={setMyId} placeholder="Ev sahibi varsayılır" />
                        </div>
                    </div>
                    <div className="space-y-4">
                        <div className="space-y-1.5">
                            <Label className="text-xs">Simülasyon Türü</Label>
                            <select
                                value={simType}
                                onChange={(e) => setSimType(e.target.value)}
                                className="h-9 w-full rounded-md border border-[var(--border)] bg-[var(--input-bg)] px-3 py-1 text-sm shadow-sm text-white focus:outline-none focus:ring-1 focus:ring-ring"
                            >
                                <option value="attack_organization">Hücum Organizasyonu</option>
                                <option value="defense_organization">Savunma Organizasyonu</option>
                                <option value="counter_attack">Kontra Atak</option>
                                <option value="set_piece_attack">Duran Top (Hücum)</option>
                                <option value="set_piece_defense">Duran Top (Savunma)</option>
                                <option value="all">Genel Taktik Mantığı</option>
                            </select>
                        </div>
                        <div className="space-y-1.5">
                            <Label className="text-xs text-[var(--muted-foreground)]">Rapor Referansı (Opsiyonel)</Label>
                            <MatchSelect 
                                value={matchId} 
                                onChange={setMatchId} 
                                placeholder="Analiz raporu seçin"
                            />
                        </div>
                        <div className="space-y-1.5">
                            <Label className="text-xs">Üretilecek Varyasyon Adedi</Label>
                            <Input 
                                type="number" 
                                min={1} max={5} 
                                value={count} 
                                onChange={(e) => setCount(Number(e.target.value) || 1)} 
                                className="h-9 w-20"
                            />
                        </div>
                    </div>
                </div>
                
                <div className="space-y-1.5">
                    <Label className="text-xs">Teknik Direktör Yorumu / Özel Talimatlar (LLM'e İletilir)</Label>
                    <Textarea 
                        placeholder="Örn: 'Takım 4-4-2 kalsın ama sol kanat oyuncusu h11 içe kat etsin, rakip sağ beki a2 üzerine çeksin...'"
                        value={coachInstruction}
                        onChange={(e) => setCoachInstruction(e.target.value)}
                        className="min-h-[80px] text-xs bg-black/20"
                    />
                </div>
                
                <Separator className="opacity-50" />
                
                <div className="flex justify-end">
                    <Button onClick={handleGenerate} disabled={loading} className="gap-2 bg-gradient-to-r from-cyan-600 to-blue-700 hover:from-cyan-500 hover:to-blue-600">
                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                        Üretimi Başlat
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}

function ManualJsonEditor() {
  const [jsonText, setJsonText] = useState(() =>
    JSON.stringify(DEFAULT_SIM_FRAMES, null, 2)
  );

  const frames = useMemo(() => {
    try {
      const parsed = JSON.parse(jsonText) as unknown;
      if (!Array.isArray(parsed)) return [];
      return parsed as SimFrame[];
    } catch {
      return [];
    }
  }, [jsonText]);

  const valid = useMemo(
    () =>
      frames.every(
        (f) =>
          typeof f.timestamp === "number" &&
          f.positions &&
          typeof f.positions === "object"
      ),
    [frames]
  );

  return (
    <div className="space-y-6">
      <Card className="border-[var(--border)] bg-[var(--card)]">
        <CardHeader>
          <CardTitle className="text-base">Manuel JSON Simülasyonu</CardTitle>
          <CardDescription className="text-xs">
            Koordinatlar normalize (0–1), zaman damgaları milisaniye.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1.5">
            <Label className="text-xs">Keyframes</Label>
            <Textarea
              value={jsonText}
              onChange={(e) => setJsonText(e.target.value)}
              className="min-h-[200px] font-mono text-xs"
              spellCheck={false}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() =>
                setJsonText(JSON.stringify(DEFAULT_SIM_FRAMES, null, 2))
              }
            >
              Örneği yükle
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                if (!valid) {
                  toast.error("JSON geçersiz veya kare formatı hatalı");
                  return;
                }
                toast.success(`${frames.length} kare hazır`);
              }}
            >
              Doğrula
            </Button>
          </div>
        </CardContent>
      </Card>

      <TacticalSimulationEngine frames={valid ? frames : []} />
    </div>
  );
}

export default function SimulationPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white">
          Taktik Simülasyon
        </h1>
        <p className="text-sm text-[var(--muted-foreground)]">
          Analiz edilen maçları seçerek taktiksel animasyonları izleyin veya yeni varyasyonlar üretin.
        </p>
      </div>

      <Tabs defaultValue="list" className="w-full">
        <TabsList className="bg-[var(--card)] border border-[var(--border)]">
          <TabsTrigger value="list">Maç Listesi & İzle</TabsTrigger>
          <TabsTrigger value="ai">Özel Taktik Üret</TabsTrigger>
          <TabsTrigger value="manual">Manuel Editor (JSON)</TabsTrigger>
        </TabsList>

        <TabsContent value="list" className="mt-4">
          <Suspense fallback={<Loader2 className="h-6 w-6 animate-spin mx-auto mt-20" />}>
            <MatchSimulationsList />
          </Suspense>
        </TabsContent>

        <TabsContent value="ai" className="mt-4">
          <SpecialAIProduction />
        </TabsContent>

        <TabsContent value="manual" className="mt-4">
          <ManualJsonEditor />
        </TabsContent>
      </Tabs>
    </div>
  );
}
