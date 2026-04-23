"use client";

import { useQuery } from "@tanstack/react-query";
import { matchAnalysesApi } from "@/lib/api-client";
import { useState, useMemo } from "react";
import { Check, ChevronsUpDown, Loader2, Search, History } from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "./ui/scroll-area";
import { Badge } from "./ui/badge";

export function MatchSelect({
  value,
  onChange,
  placeholder = "Geçmiş analizlerden seçin...",
  className,
}: {
  value: string | number;
  onChange: (matchId: string) => void;
  placeholder?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");

  const matchesQ = useQuery({
    queryKey: ["all-analyses-select"],
    queryFn: () => matchAnalysesApi.list({ page: 1, page_size: 100 }),
    staleTime: 60_000,
  });

  const items = matchesQ.data?.items ?? [];
  
  const filtered = useMemo(() => {
    if (!q) return items;
    const lowQ = q.toLowerCase();
    return items.filter(m => 
        (m.home_name?.toLowerCase().includes(lowQ)) || 
        (m.away_name?.toLowerCase().includes(lowQ)) ||
        (String(m.match_id).includes(lowQ))
    );
  }, [items, q]);

  const selectedMatch = useMemo(() => 
    items.find(m => String(m.match_id) === String(value)),
  [items, value]);

  return (
    <div className={cn("relative w-full", className)}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-9 w-full items-center justify-between rounded-md border border-[var(--border)] bg-[var(--card)] px-3 py-1 text-xs shadow-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50 text-white"
      >
        <div className="flex items-center gap-2 truncate">
          <History className="h-3 w-3 opacity-50" />
          <span className="truncate">
            {selectedMatch ? 
              `${selectedMatch.home_name} vs ${selectedMatch.away_name} (#${selectedMatch.match_id})` : 
              placeholder
            }
          </span>
        </div>
        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
      </button>

      {open && (
        <div className="absolute top-10 z-50 w-full rounded-md border border-[var(--border)] bg-[#0c1421] shadow-xl animate-in fade-in zoom-in-95 duration-100">
          <div className="flex items-center border-b border-[var(--border)] px-3 py-2">
            <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
            <input
              className="flex h-7 w-full rounded-md bg-transparent text-sm outline-none placeholder:text-muted-foreground text-white"
              placeholder="Takım veya ID ara..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              autoFocus
            />
          </div>
          <ScrollArea className="max-h-[300px] overflow-auto py-1">
            {matchesQ.isLoading ? (
              <div className="flex items-center justify-center py-6 text-xs text-[var(--muted-foreground)]">
                <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                Yükleniyor...
              </div>
            ) : filtered.length === 0 ? (
              <div className="py-6 text-center text-xs text-[var(--muted-foreground)]">
                Analiz bulunamadı.
              </div>
            ) : (
              filtered.map((m) => (
                <div
                  key={m.id}
                  onClick={() => {
                    onChange(String(m.match_id));
                    setOpen(false);
                  }}
                  className={cn(
                    "flex cursor-pointer flex-col gap-0.5 px-3 py-2 text-xs transition-colors hover:bg-white/10",
                    String(m.match_id) === String(value) && "bg-cyan-500/10 text-cyan-400"
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium truncate">
                        {m.home_name} vs {m.away_name}
                    </span>
                    <Badge variant="outline" className="text-[9px] font-mono py-0 h-4">#{m.match_id}</Badge>
                  </div>
                  <span className="text-[10px] opacity-60">
                    {m.match_date || "Tarih belirtilmedi"}
                  </span>
                </div>
              ))
            )}
          </ScrollArea>
        </div>
      )}
      
      {open && (
        <div 
          className="fixed inset-0 z-40" 
          onClick={() => setOpen(false)} 
        />
      )}
    </div>
  );
}
