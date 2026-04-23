"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, Pencil, RefreshCw, Search, Trash2 } from "lucide-react";
import {
  PAGE_SIZE,
  restApi,
  syncLeaguesFromApi,
  syncTeamsFromApi,
  syncPlayersFromApi,
  syncPlayerStatsFromApi,
  type League,
  type Paginated,
  type Team,
  type Player,
} from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export default function DataPage() {
  const qc = useQueryClient();
  const [season, setSeason] = useState(2024);
  const [leagueFilter, setLeagueFilter] = useState<number | "">("");
  const [teamForPlayers, setTeamForPlayers] = useState<number | "">("");
  const [leagueForStats, setLeagueForStats] = useState<number | "">("");

  const [leagueSearch, setLeagueSearch] = useState("");
  const [leagueSearchDebounced, setLeagueSearchDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setLeagueSearchDebounced(leagueSearch.trim()), 350);
    return () => clearTimeout(t);
  }, [leagueSearch]);
  const [leaguePage, setLeaguePage] = useState(1);
  useEffect(() => {
    setLeaguePage(1);
  }, [leagueSearchDebounced]);

  const [teamSearch, setTeamSearch] = useState("");
  const [teamSearchDebounced, setTeamSearchDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setTeamSearchDebounced(teamSearch.trim()), 350);
    return () => clearTimeout(t);
  }, [teamSearch]);
  const [teamPage, setTeamPage] = useState(1);
  useEffect(() => {
    setTeamPage(1);
  }, [teamSearchDebounced, leagueFilter]);

  const leaguesQ = useQuery({
    queryKey: ["leagues", leagueSearchDebounced, leaguePage],
    queryFn: () =>
      restApi.leagues({
        q: leagueSearchDebounced || undefined,
        page: leaguePage,
        page_size: PAGE_SIZE,
      }),
  });

  const teamsQ = useQuery({
    queryKey: ["teams", leagueFilter, teamSearchDebounced, teamPage],
    queryFn: () =>
      restApi.teams({
        league_id: leagueFilter === "" ? undefined : Number(leagueFilter),
        q: teamSearchDebounced || undefined,
        page: teamPage,
        page_size: PAGE_SIZE,
      }),
  });
  const playersQ = useQuery({
    queryKey: ["players", teamForPlayers],
    queryFn: () => restApi.players(Number(teamForPlayers)),
    enabled: teamForPlayers !== "",
  });

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["leagues"] });
    void qc.invalidateQueries({ queryKey: ["teams"] });
    void qc.invalidateQueries({ queryKey: ["players"] });
  };

  const syncLeagues = useMutation({
    mutationFn: () => syncLeaguesFromApi(season),
    onSuccess: (r) => {
      toast.success(r.message || "Ligler senkronize edildi");
      void qc.invalidateQueries({ queryKey: ["leagues"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const syncTeams = useMutation({
    mutationFn: () => {
      if (leagueFilter === "") throw new Error("Takım senkronu için lig seçin");
      return syncTeamsFromApi(Number(leagueFilter), season);
    },
    onSuccess: (r) => {
      toast.success(r.message || "Takımlar güncellendi");
      void qc.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const syncPlayers = useMutation({
    mutationFn: () => {
      if (teamForPlayers === "") throw new Error("Oyuncu senkronu için takım seçin");
      return syncPlayersFromApi(Number(teamForPlayers), season);
    },
    onSuccess: (r) => {
      toast.success(r.message || "Oyuncular güncellendi");
      void qc.invalidateQueries({ queryKey: ["players"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const syncStats = useMutation({
    mutationFn: () => {
      if (teamForPlayers === "" || leagueForStats === "")
        throw new Error("Oyuncu istatistiği için takım ve lig ID gerekli");
      return syncPlayerStatsFromApi(
        Number(teamForPlayers),
        season,
        Number(leagueForStats)
      );
    },
    onSuccess: (r) => {
      toast.success(r.message || "İstatistikler güncellendi");
      void qc.invalidateQueries({ queryKey: ["players"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white">Veri yönetimi</h1>
        <p className="text-sm text-[var(--muted-foreground)]">
          Senkron uçları: <code className="text-xs">/leagues|teams|players|playerstats/fetch_and_upsert</code>
        </p>
      </div>

      <Card className="border-[var(--border)] bg-[var(--card)]">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Sezon & senkron</CardTitle>
          <CardDescription className="text-xs">
            Harici futbol API anahtarınız backend .env içinde olmalı. DataService yoksa senkron 500 dönebilir.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Sezon (yıl)</Label>
            <Input
              type="number"
              className="h-9 w-28"
              value={season}
              onChange={(e) => setSeason(Number(e.target.value))}
            />
          </div>
          <Button
            size="sm"
            variant="secondary"
            disabled={syncLeagues.isPending}
            onClick={() => syncLeagues.mutate()}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${syncLeagues.isPending ? "animate-spin" : ""}`} />
            Ligleri API’den çek
          </Button>
          <Button size="sm" variant="outline" onClick={() => invalidateAll()}>
            Tabloları yenile
          </Button>
        </CardContent>
      </Card>

      <Tabs defaultValue="leagues" className="w-full">
        <TabsList>
          <TabsTrigger value="leagues">Ligler</TabsTrigger>
          <TabsTrigger value="teams">Takımlar</TabsTrigger>
          <TabsTrigger value="players">Oyuncular</TabsTrigger>
        </TabsList>

        <TabsContent value="leagues">
          <LeaguesTable
            data={leaguesQ.data}
            loading={leaguesQ.isLoading}
            search={leagueSearch}
            onSearchChange={setLeagueSearch}
            page={leaguePage}
            onPageChange={setLeaguePage}
            onRefresh={() => void leaguesQ.refetch()}
          />
        </TabsContent>

        <TabsContent value="teams" className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Lig filtresi (ID)</Label>
              <Input
                className="h-9 w-36"
                placeholder="boş = tümü"
                value={leagueFilter === "" ? "" : leagueFilter}
                onChange={(e) =>
                  setLeagueFilter(e.target.value === "" ? "" : Number(e.target.value))
                }
              />
            </div>
            <Button
              size="sm"
              variant="secondary"
              disabled={syncTeams.isPending || leagueFilter === ""}
              onClick={() => syncTeams.mutate()}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${syncTeams.isPending ? "animate-spin" : ""}`} />
              Takımları API’den çek
            </Button>
          </div>
          <TeamsTable
            data={teamsQ.data}
            loading={teamsQ.isLoading}
            search={teamSearch}
            onSearchChange={setTeamSearch}
            page={teamPage}
            onPageChange={setTeamPage}
            onRefresh={() => void teamsQ.refetch()}
          />
        </TabsContent>

        <TabsContent value="players" className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Takım ID</Label>
              <Input
                className="h-9 w-36"
                placeholder="örn. 645"
                value={teamForPlayers === "" ? "" : teamForPlayers}
                onChange={(e) =>
                  setTeamForPlayers(e.target.value === "" ? "" : Number(e.target.value))
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Lig ID (istatistik senkron)</Label>
              <Input
                className="h-9 w-36"
                placeholder="örn. 203"
                value={leagueForStats === "" ? "" : leagueForStats}
                onChange={(e) =>
                  setLeagueForStats(e.target.value === "" ? "" : Number(e.target.value))
                }
              />
            </div>
            <Button
              size="sm"
              variant="secondary"
              disabled={syncPlayers.isPending || teamForPlayers === ""}
              onClick={() => syncPlayers.mutate()}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${syncPlayers.isPending ? "animate-spin" : ""}`} />
              Oyuncuları çek
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={syncStats.isPending || teamForPlayers === "" || leagueForStats === ""}
              onClick={() => syncStats.mutate()}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${syncStats.isPending ? "animate-spin" : ""}`} />
              Oyuncu istatistikleri
            </Button>
          </div>
          <PlayersTable
            rows={playersQ.data ?? []}
            loading={playersQ.isFetching}
            enabled={teamForPlayers !== ""}
            onRefresh={() => void playersQ.refetch()}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function PaginationBar({
  total,
  page,
  pageSize,
  onPageChange,
}: {
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (p: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const p = Math.min(Math.max(1, page), totalPages);
  return (
    <div className="flex flex-col gap-2 border-t border-[var(--border)] pt-3 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-xs text-[var(--muted-foreground)]">
        Toplam <span className="font-medium text-[var(--foreground)]">{total}</span> kayıt · Sayfa{" "}
        <span className="font-medium text-[var(--foreground)]">{p}</span> / {totalPages} · Sayfa başı{" "}
        {pageSize}
      </p>
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={p <= 1}
          onClick={() => onPageChange(p - 1)}
        >
          <ChevronLeft className="h-4 w-4" />
          Önceki
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={p >= totalPages}
          onClick={() => onPageChange(p + 1)}
        >
          Sonraki
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

function LeaguesTable({
  data,
  loading,
  search,
  onSearchChange,
  page,
  onPageChange,
  onRefresh,
}: {
  data: Paginated<League> | undefined;
  loading: boolean;
  search: string;
  onSearchChange: (v: string) => void;
  page: number;
  onPageChange: (p: number) => void;
  onRefresh: () => void;
}) {
  const rows = data?.items ?? [];
  const total = data?.total ?? 0;
  const pageSize = data?.page_size ?? PAGE_SIZE;

  const qc = useQueryClient();
  const [edit, setEdit] = useState<League | null>(null);
  const [del, setDel] = useState<League | null>(null);
  const [form, setForm] = useState({ name: "", country: "", season: "" });

  const patch = useMutation({
    mutationFn: () =>
      restApi.patchLeague(edit!.id, {
        name: form.name || undefined,
        country: form.country || undefined,
        season: form.season || undefined,
      }),
    onSuccess: () => {
      toast.success("Lig güncellendi");
      setEdit(null);
      void qc.invalidateQueries({ queryKey: ["leagues"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const remove = useMutation({
    mutationFn: () => restApi.deleteLeague(del!.id),
    onSuccess: () => {
      toast.success("Lig silindi");
      setDel(null);
      void qc.invalidateQueries({ queryKey: ["leagues"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Card className="border-[var(--border)] bg-[var(--card)]">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Ligler</CardTitle>
        <Button size="sm" variant="ghost" onClick={onRefresh}>
          Yenile
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <Input
            className="h-9 pl-8 text-sm"
            placeholder="Ara: ad, ülke, sezon veya lig ID…"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        </div>
        <ScrollArea className="h-[420px] w-full rounded-md border border-[var(--border)]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Ad</TableHead>
                <TableHead>Ülke</TableHead>
                <TableHead>Sezon</TableHead>
                <TableHead className="w-[100px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ?
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-xs text-[var(--muted-foreground)]">
                    Yükleniyor…
                  </TableCell>
                </TableRow>
              : rows.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-mono text-xs">{r.id}</TableCell>
                    <TableCell>{r.name}</TableCell>
                    <TableCell className="text-xs text-[var(--muted-foreground)]">
                      {r.country ?? "—"}
                    </TableCell>
                    <TableCell className="text-xs">{r.season ?? "—"}</TableCell>
                    <TableCell className="space-x-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={() => {
                          setEdit(r);
                          setForm({
                            name: r.name,
                            country: r.country ?? "",
                            season: r.season ?? "",
                          });
                        }}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8 text-red-400"
                        onClick={() => setDel(r)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </ScrollArea>

        <PaginationBar
          total={total}
          page={page}
          pageSize={pageSize}
          onPageChange={onPageChange}
        />

        <Dialog open={!!edit} onOpenChange={() => setEdit(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Lig düzenle</DialogTitle>
            </DialogHeader>
            <div className="grid gap-3 py-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Ad</Label>
                <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Ülke</Label>
                <Input
                  value={form.country}
                  onChange={(e) => setForm((f) => ({ ...f, country: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Sezon</Label>
                <Input
                  value={form.season}
                  onChange={(e) => setForm((f) => ({ ...f, season: e.target.value }))}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setEdit(null)}>
                İptal
              </Button>
              <Button disabled={patch.isPending} onClick={() => patch.mutate()}>
                Kaydet
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={!!del} onOpenChange={() => setDel(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Ligi sil?</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-[var(--muted-foreground)]">
              {del?.name} — bağlı takım yoksa silinir.
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDel(null)}>
                İptal
              </Button>
              <Button variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate()}>
                Sil
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}

function TeamsTable({
  data,
  loading,
  search,
  onSearchChange,
  page,
  onPageChange,
  onRefresh,
}: {
  data: Paginated<Team> | undefined;
  loading: boolean;
  search: string;
  onSearchChange: (v: string) => void;
  page: number;
  onPageChange: (p: number) => void;
  onRefresh: () => void;
}) {
  const rows = data?.items ?? [];
  const total = data?.total ?? 0;
  const pageSize = data?.page_size ?? PAGE_SIZE;

  const qc = useQueryClient();
  const [edit, setEdit] = useState<Team | null>(null);
  const [del, setDel] = useState<Team | null>(null);
  const [form, setForm] = useState({ name: "", country: "", league_id: "" });

  const patch = useMutation({
    mutationFn: () =>
      restApi.patchTeam(edit!.id, {
        name: form.name || undefined,
        country: form.country || undefined,
        league_id: form.league_id ? Number(form.league_id) : undefined,
      }),
    onSuccess: () => {
      toast.success("Takım güncellendi");
      setEdit(null);
      void qc.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const remove = useMutation({
    mutationFn: () => restApi.deleteTeam(del!.id),
    onSuccess: () => {
      toast.success("Takım silindi");
      setDel(null);
      void qc.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Card className="border-[var(--border)] bg-[var(--card)]">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Takımlar</CardTitle>
        <Button size="sm" variant="ghost" onClick={onRefresh}>
          Yenile
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <Input
            className="h-9 pl-8 text-sm"
            placeholder="Ara: takım adı, ülke, takım/lig ID…"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        </div>
        <ScrollArea className="h-[420px] w-full rounded-md border border-[var(--border)]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Lig</TableHead>
                <TableHead>Ad</TableHead>
                <TableHead>Ülke</TableHead>
                <TableHead className="w-[100px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ?
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-xs">
                    Yükleniyor…
                  </TableCell>
                </TableRow>
              : rows.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-mono text-xs">{r.id}</TableCell>
                    <TableCell className="text-xs">{r.league_id}</TableCell>
                    <TableCell>{r.name}</TableCell>
                    <TableCell className="text-xs text-[var(--muted-foreground)]">
                      {r.country ?? "—"}
                    </TableCell>
                    <TableCell className="space-x-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={() => {
                          setEdit(r);
                          setForm({
                            name: r.name,
                            country: r.country ?? "",
                            league_id: String(r.league_id),
                          });
                        }}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8 text-red-400"
                        onClick={() => setDel(r)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </ScrollArea>

        <PaginationBar
          total={total}
          page={page}
          pageSize={pageSize}
          onPageChange={onPageChange}
        />

        <Dialog open={!!edit} onOpenChange={() => setEdit(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Takım düzenle</DialogTitle>
            </DialogHeader>
            <div className="grid gap-3 py-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Ad</Label>
                <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Ülke</Label>
                <Input
                  value={form.country}
                  onChange={(e) => setForm((f) => ({ ...f, country: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Lig ID</Label>
                <Input
                  value={form.league_id}
                  onChange={(e) => setForm((f) => ({ ...f, league_id: e.target.value }))}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setEdit(null)}>
                İptal
              </Button>
              <Button disabled={patch.isPending} onClick={() => patch.mutate()}>
                Kaydet
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={!!del} onOpenChange={() => setDel(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Takımı sil?</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-[var(--muted-foreground)]">{del?.name}</p>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDel(null)}>
                İptal
              </Button>
              <Button variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate()}>
                Sil
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}

function PlayersTable({
  rows,
  loading,
  enabled,
  onRefresh,
}: {
  rows: Player[];
  loading: boolean;
  enabled: boolean;
  onRefresh: () => void;
}) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState<Player | null>(null);
  const [del, setDel] = useState<Player | null>(null);
  const [form, setForm] = useState({
    firstname: "",
    lastname: "",
    position: "",
    description: "",
    rating: "",
    minutes: "",
    appearances: "",
  });

  const openEdit = (p: Player) => {
    setEdit(p);
    const g = (p.games || {}) as Record<string, unknown>;
    setForm({
      firstname: p.firstname ?? "",
      lastname: p.lastname ?? "",
      position: p.position ?? "",
      description: p.description ?? "",
      rating: g.rating != null ? String(g.rating) : "",
      minutes: g.minutes != null ? String(g.minutes) : "",
      appearances: g.appearences != null ? String(g.appearences) : "",
    });
  };

  const patchPlayer = useMutation({
    mutationFn: async () => {
      await restApi.patchPlayer(edit!.id, {
        firstname: form.firstname || undefined,
        lastname: form.lastname || undefined,
        position: form.position || undefined,
        description: form.description || undefined,
      });
      const games: Record<string, unknown> = {};
      if (form.rating) games.rating = Number(form.rating);
      if (form.minutes) games.minutes = Number(form.minutes);
      if (form.appearances) games.appearences = Number(form.appearances);
      if (Object.keys(games).length)
        await restApi.patchPlayerStats(edit!.id, { games });
    },
    onSuccess: () => {
      toast.success("Oyuncu güncellendi");
      setEdit(null);
      void qc.invalidateQueries({ queryKey: ["players"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const remove = useMutation({
    mutationFn: () => restApi.deletePlayer(del!.id),
    onSuccess: () => {
      toast.success("Oyuncu silindi");
      setDel(null);
      void qc.invalidateQueries({ queryKey: ["players"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!enabled) {
    return (
      <p className="text-sm text-[var(--muted-foreground)]">Oyuncu listesi için takım ID girin.</p>
    );
  }

  return (
    <Card className="border-[var(--border)] bg-[var(--card)]">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">Oyuncular</CardTitle>
        <Button size="sm" variant="ghost" onClick={onRefresh}>
          Yenile
        </Button>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[480px] w-full rounded-md border border-[var(--border)]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>İsim</TableHead>
                <TableHead>Poz</TableHead>
                <TableHead>Rating</TableHead>
                <TableHead>Dk</TableHead>
                <TableHead className="w-[100px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ?
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-xs">
                    Yükleniyor…
                  </TableCell>
                </TableRow>
              : rows.map((p) => {
                  const g = (p.games || {}) as Record<string, unknown>;
                  return (
                    <TableRow key={p.id}>
                      <TableCell className="font-mono text-xs">{p.id}</TableCell>
                      <TableCell className="text-sm">
                        {p.firstname} {p.lastname}
                      </TableCell>
                      <TableCell className="text-xs">{p.position ?? "—"}</TableCell>
                      <TableCell className="text-xs">{String(g.rating ?? "—")}</TableCell>
                      <TableCell className="text-xs">{String(g.minutes ?? "—")}</TableCell>
                      <TableCell className="space-x-1">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8"
                          onClick={() => openEdit(p)}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8 text-red-400"
                          onClick={() => setDel(p)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
            </TableBody>
          </Table>
        </ScrollArea>

        <Separator className="my-4" />

        <Dialog open={!!edit} onOpenChange={() => setEdit(null)}>
          <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Oyuncu düzenle</DialogTitle>
            </DialogHeader>
            <div className="grid gap-3 py-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Ad</Label>
                  <Input
                    value={form.firstname}
                    onChange={(e) => setForm((f) => ({ ...f, firstname: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Soyad</Label>
                  <Input
                    value={form.lastname}
                    onChange={(e) => setForm((f) => ({ ...f, lastname: e.target.value }))}
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Pozisyon</Label>
                <Input
                  value={form.position}
                  onChange={(e) => setForm((f) => ({ ...f, position: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">TD notu</Label>
                <Input
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                />
              </div>
              <p className="text-xs text-[var(--muted-foreground)]">games JSON alanı (kısmi güncelleme)</p>
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Rating</Label>
                  <Input
                    value={form.rating}
                    onChange={(e) => setForm((f) => ({ ...f, rating: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Dakika</Label>
                  <Input
                    value={form.minutes}
                    onChange={(e) => setForm((f) => ({ ...f, minutes: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Maç</Label>
                  <Input
                    value={form.appearances}
                    onChange={(e) => setForm((f) => ({ ...f, appearances: e.target.value }))}
                  />
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setEdit(null)}>
                İptal
              </Button>
              <Button disabled={patchPlayer.isPending} onClick={() => patchPlayer.mutate()}>
                Kaydet
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={!!del} onOpenChange={() => setDel(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Oyuncuyu sil?</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-[var(--muted-foreground)]">
              {del?.firstname} {del?.lastname}
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDel(null)}>
                İptal
              </Button>
              <Button variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate()}>
                Sil
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}
