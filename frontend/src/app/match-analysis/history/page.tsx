"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, ChevronLeft, ChevronRight, Trash2, FileText, ArrowLeft } from "lucide-react";
import { matchAnalysesApi, type MatchAnalysisMeta, type MatchAnalysisDetail } from "@/lib/api-client";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";

const PAGE_SIZE = 20;

function AnalysisDetailPanel({
  analysis,
  onClose,
}: {
  analysis: MatchAnalysisDetail;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <Card className="w-full max-w-3xl border-[var(--border)] bg-[#070f1c] shadow-2xl">
        <CardHeader className="flex flex-row items-center justify-between gap-3 pb-3">
          <div>
            <CardTitle className="text-base text-white">Taktik Analiz Raporu</CardTitle>
            <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
              {analysis.home_name ?? `Takım ${analysis.home_id}`}{" "}
              <span className="text-[var(--muted-foreground)]">vs</span>{" "}
              {analysis.away_name ?? `Takım ${analysis.away_id}`}
              {analysis.created_at && (
                <span className="ml-2 opacity-60">
                  · {new Date(analysis.created_at).toLocaleString("tr-TR")}
                </span>
              )}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <ArrowLeft className="h-4 w-4 mr-1" /> Geri
          </Button>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[60vh] w-full rounded-md border border-[var(--border)] bg-black/30 p-4">
            <pre className="whitespace-pre-wrap text-sm text-cyan-100/90 font-sans leading-relaxed">
              {analysis.result_text}
            </pre>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}

function AnalysisRow({
  row,
  onInspect,
  onDelete,
}: {
  row: MatchAnalysisMeta;
  onInspect: (id: number) => void;
  onDelete: (id: number) => void;
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-lg border border-[var(--border)] bg-black/20 px-4 py-3 text-sm">
      <div className="flex flex-col gap-0.5 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-emerald-300/90 truncate">
            {row.home_name ?? `Takım ${row.home_id}`}
          </span>
          <span className="text-[var(--muted-foreground)] text-xs">vs</span>
          <span className="font-medium text-violet-300/90 truncate">
            {row.away_name ?? `Takım ${row.away_id}`}
          </span>
          <Badge variant="outline" className="text-[10px] font-mono border-[var(--border)]">
            #{row.match_id}
          </Badge>
        </div>
        <span className="text-[11px] text-[var(--muted-foreground)]">
          {row.created_at ? new Date(row.created_at).toLocaleString("tr-TR") : "—"}
        </span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <Button
          size="sm"
          variant="secondary"
          className="h-8 gap-1.5"
          onClick={() => onInspect(row.id)}
        >
          <FileText className="h-3.5 w-3.5" />
          İncele
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8 text-red-400 hover:text-red-300 hover:bg-red-400/10"
          onClick={() => onDelete(row.id)}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

export default function MatchAnalysisHistoryPage() {
  const [matchId] = useState<number>(0); // 0 = all
  const [page, setPage] = useState(1);
  const [selectedDetail, setSelectedDetail] = useState<MatchAnalysisDetail | null>(null);
  const [loadingId, setLoadingId] = useState<number | null>(null);

  // matchId=0 → hepsi; matchAnalysesApi.list bunu desteklemiyor olabilir,
  // o yüzden matchId=0 ise isteği atlamayı ve boş array döndürmeyi
  // burada handle edip backend'de "geçmiş hepsini getir" endpoint'i ekleyeceğiz.
  // Şimdilik match_id=0 ile istek atıyoruz — backend'in bunu ignore etmesini bekleyeceğiz.
  const historyQ = useQuery({
    queryKey: ["match-analyses-all", page],
    queryFn: () => matchAnalysesApi.list({ page, page_size: PAGE_SIZE }),
  });

  const totalPages = historyQ.data
    ? Math.max(1, Math.ceil(historyQ.data.total / PAGE_SIZE))
    : 1;

  const handleInspect = async (id: number) => {
    setLoadingId(id);
    try {
      const detail = await matchAnalysesApi.get(id);
      setSelectedDetail(detail);
    } catch (e: any) {
      toast.error(e.message || "Rapor yüklenemedi");
    } finally {
      setLoadingId(null);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await matchAnalysesApi.delete(id);
      toast.success("Analiz silindi");
      historyQ.refetch();
      if (selectedDetail?.id === id) setSelectedDetail(null);
    } catch (e: any) {
      toast.error(e.message || "Silinemedi");
    }
  };

  const items = historyQ.data?.items ?? [];

  return (
    <>
      {selectedDetail && (
        <AnalysisDetailPanel
          analysis={selectedDetail}
          onClose={() => setSelectedDetail(null)}
        />
      )}

      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">Geçmiş Taktik Analizler</h1>
            <p className="text-sm text-[var(--muted-foreground)] mt-0.5">
              Tüm maçlara ait analiz raporları — en yeniden en eskiye
            </p>
          </div>
          <Link href="/match-analysis">
            <Button variant="outline" size="sm">
              <ArrowLeft className="h-4 w-4 mr-1.5" /> Yeni Analiz
            </Button>
          </Link>
        </div>

        {/* Content Card */}
        <Card className="border-[var(--border)] bg-[var(--card)]/80">
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <CardTitle className="text-sm text-[var(--muted-foreground)] font-normal">
              {historyQ.data ? (
                <span>
                  Toplam <span className="text-white font-semibold">{historyQ.data.total}</span> analiz · Sayfa{" "}
                  <span className="text-white font-semibold">{page}</span> / {totalPages}
                </span>
              ) : (
                "Yükleniyor..."
              )}
            </CardTitle>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => historyQ.refetch()}
              disabled={historyQ.isFetching}
            >
              {historyQ.isFetching ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                  <path d="M3 3v5h5" />
                  <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
                  <path d="M16 16h5v5" />
                </svg>
              )}
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {historyQ.isLoading && (
              <div className="flex items-center gap-2 text-sm text-[var(--muted-foreground)] py-8 justify-center">
                <Loader2 className="h-4 w-4 animate-spin" /> Analizler yükleniyor...
              </div>
            )}

            {!historyQ.isLoading && items.length === 0 && (
              <div className="py-12 text-center">
                <p className="text-sm text-[var(--muted-foreground)]">Henüz kayıtlı analiz bulunmuyor.</p>
                <Link href="/match-analysis">
                  <Button variant="secondary" size="sm" className="mt-3">
                    İlk Analizi Yap
                  </Button>
                </Link>
              </div>
            )}

            {items.map((row) => (
              <AnalysisRow
                key={row.id}
                row={row}
                onInspect={handleInspect}
                onDelete={handleDelete}
              />
            ))}

            {loadingId !== null && (
              <div className="flex justify-center py-2">
                <Loader2 className="h-4 w-4 animate-spin text-[var(--muted-foreground)]" />
              </div>
            )}
          </CardContent>
        </Card>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1 || historyQ.isFetching}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>

            {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
              // Show pages around current
              let pageNum: number;
              if (totalPages <= 7) {
                pageNum = i + 1;
              } else if (page <= 4) {
                pageNum = i + 1;
              } else if (page >= totalPages - 3) {
                pageNum = totalPages - 6 + i;
              } else {
                pageNum = page - 3 + i;
              }
              return (
                <Button
                  key={pageNum}
                  variant={pageNum === page ? "default" : "outline"}
                  size="sm"
                  className="w-9"
                  onClick={() => setPage(pageNum)}
                  disabled={historyQ.isFetching}
                >
                  {pageNum}
                </Button>
              );
            })}

            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages || historyQ.isFetching}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </>
  );
}
