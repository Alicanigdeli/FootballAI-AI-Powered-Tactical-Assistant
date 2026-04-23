"use client";

import { useQuery } from "@tanstack/react-query";
import { restApi } from "@/lib/api-client";
import { Input } from "@/components/ui/input";
import { useState, useMemo } from "react";
import { Check, ChevronsUpDown, Loader2, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "./ui/scroll-area";

export function TeamSelect({
  value,
  onChange,
  placeholder = "Takım seçin...",
  className,
}: {
  value: string | number;
  onChange: (id: string) => void;
  placeholder?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");

  const teamsQ = useQuery({
    queryKey: ["all-teams-select"],
    queryFn: () => restApi.teams({ page_size: 1000 }), // Get all for easy filtering
    staleTime: 300_000,
  });

  const teams = teamsQ.data?.items ?? [];
  
  const filtered = useMemo(() => {
    if (!q) return teams;
    const lowQ = q.toLowerCase();
    return teams.filter(t => t.name.toLowerCase().includes(lowQ));
  }, [teams, q]);

  const selectedTeam = useMemo(() => 
    teams.find(t => String(t.id) === String(value)),
  [teams, value]);

  return (
    <div className={cn("relative w-full", className)}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-9 w-full items-center justify-between rounded-md border border-[var(--border)] bg-[var(--input-bg)] px-3 py-1 text-sm shadow-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50 text-white"
      >
        <span className="truncate">
          {selectedTeam ? selectedTeam.name : placeholder}
        </span>
        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
      </button>

      {open && (
        <div className="absolute top-10 z-50 w-full rounded-md border border-[var(--border)] bg-[#0c1421] shadow-xl animate-in fade-in zoom-in-95 duration-100">
          <div className="flex items-center border-b border-[var(--border)] px-3 py-2">
            <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
            <input
              className="flex h-7 w-full rounded-md bg-transparent text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50 text-white"
              placeholder="Ara..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              autoFocus
            />
          </div>
          <ScrollArea className="max-h-[300px] overflow-auto py-1">
            {teamsQ.isLoading ? (
              <div className="flex items-center justify-center py-6 text-xs text-[var(--muted-foreground)]">
                <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                Yükleniyor...
              </div>
            ) : filtered.length === 0 ? (
              <div className="py-6 text-center text-xs text-[var(--muted-foreground)]">
                Takım bulunamadı.
              </div>
            ) : (
              filtered.map((team) => (
                <div
                  key={team.id}
                  onClick={() => {
                    onChange(String(team.id));
                    setOpen(false);
                  }}
                  className={cn(
                    "flex cursor-pointer items-center justify-between px-3 py-2 text-sm transition-colors hover:bg-white/10",
                    String(team.id) === String(value) && "bg-cyan-500/10 text-cyan-400"
                  )}
                >
                  <span className="truncate">{team.name}</span>
                  {String(team.id) === String(value) && <Check className="h-4 w-4" />}
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
