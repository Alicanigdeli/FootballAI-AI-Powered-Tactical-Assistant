/**
 * Python FastAPI backend — matches `backend/app.py` routes.
 */

export function getApiBase(): string {
  return (
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000"
  );
}

function url(path: string, params?: Record<string, string | number | undefined | null>) {
  const p = path.startsWith("/") ? path : `/${path}`;
  const u = new URL(`${getApiBase()}${p}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) u.searchParams.set(k, String(v));
    });
  }
  return u.toString();
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j?.detail === "string" ? j.detail : JSON.stringify(j);
    } catch {
      try {
        detail = await res.text();
      } catch {
        /* ignore */
      }
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function apiGet<T>(
  path: string,
  params?: Record<string, string | number | undefined | null>
): Promise<T> {
  const res = await fetch(url(path, params), { cache: "no-store" });
  return handle<T>(res);
}

export async function apiDelete<T>(path: string): Promise<T> {
  const res = await fetch(url(path), { method: "DELETE" });
  return handle<T>(res);
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(url(path), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<T>(res);
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(url(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<T>(res);
}

// ─── Sync (external API → PostgreSQL) — GET query params per backend ─────────

export function syncLeaguesFromApi(season: number) {
  return apiGet<{
    status: string;
    season: number;
    message?: string;
  }>("/leagues/fetch_and_upsert", { season });
}

export function syncTeamsFromApi(leagueId: number, season: number) {
  return apiGet<{
    status: string;
    league_id: number;
    season: number;
    message?: string;
  }>("/teams/fetch_and_upsert", { league_id: leagueId, season });
}

export function syncPlayersFromApi(teamId: number, season: number) {
  return apiGet<{
    status: string;
    team_id: number;
    season: number;
    message?: string;
  }>("/players/fetch_and_upsert", { team_id: teamId, season });
}

export function syncPlayerStatsFromApi(
  teamId: number,
  season: number,
  leagueId: number
) {
  return apiGet<{
    status: string;
    team_id: number;
    season: number;
    league_id: number;
    message?: string;
  }>("/playerstats/fetch_and_upsert", { team_id: teamId, season, league_id: leagueId });
}

// ─── REST CRUD ──────────────────────────────────────────────────────────────

export type League = {
  id: number;
  name: string;
  country: string | null;
  season: string | null;
};

export type Team = {
  id: number;
  league_id: number;
  name: string;
  country: string | null;
};

export type Paginated<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type Player = {
  id: number;
  team_id: number;
  firstname: string | null;
  lastname: string | null;
  age: number | null;
  nationality: string | null;
  position: string | null;
  description: string | null;
  height: number | null;
  weight: number | null;
  injured: boolean | null;
  games: Record<string, unknown> | null;
};

export const PAGE_SIZE = 50;

export const restApi = {
  leagues: (opts?: { q?: string; page?: number; page_size?: number }) =>
    apiGet<Paginated<League>>("/rest/leagues", {
      q: opts?.q || undefined,
      page: opts?.page ?? 1,
      page_size: opts?.page_size ?? PAGE_SIZE,
    }),
  patchLeague: (id: number, body: Partial<Pick<League, "name" | "country" | "season">>) =>
    apiPatch<{ status: string }>(`/rest/leagues/${id}`, body),
  deleteLeague: (id: number) => apiDelete<{ status: string }>(`/rest/leagues/${id}`),

  teams: (opts?: { league_id?: number; q?: string; page?: number; page_size?: number }) =>
    apiGet<Paginated<Team>>("/rest/teams", {
      league_id: opts?.league_id,
      q: opts?.q || undefined,
      page: opts?.page ?? 1,
      page_size: opts?.page_size ?? PAGE_SIZE,
    }),
  patchTeam: (id: number, body: Partial<Pick<Team, "name" | "country" | "league_id">>) =>
    apiPatch<{ status: string }>(`/rest/teams/${id}`, body),
  deleteTeam: (id: number) => apiDelete<{ status: string }>(`/rest/teams/${id}`),

  players: (teamId: number) => apiGet<Player[]>("/rest/players", { team_id: teamId }),
  patchPlayer: (
    id: number,
    body: Partial<
      Pick<Player, "firstname" | "lastname" | "age" | "nationality" | "position" | "description">
    >
  ) => apiPatch<{ status: string }>(`/rest/players/${id}`, body),
  patchPlayerStats: (
    id: number,
    body: Partial<{
      height: number;
      weight: number;
      injured: boolean;
      games: Record<string, unknown>;
      shooting: Record<string, unknown>;
      passing: Record<string, unknown>;
      goals: Record<string, unknown>;
      tackles: Record<string, unknown>;
    }>
  ) => apiPatch<{ status: string }>(`/rest/players/${id}/statistics`, body),
  deletePlayer: (id: number) => apiDelete<{ status: string }>(`/rest/players/${id}`),
};

// ─── Coach + RAG ────────────────────────────────────────────────────────────

export type MatchStrategyBody = {
  match_id: number;
  home_id: number;
  away_id: number;
  my_team_id: number;
  match_date?: string | null;
  /** Aynı maçta /coach/match-chat için oturum (UUID önerilir) */
  session_id?: string | null;
  coach_instruction?: string | null;
  analysis_notes?: string | null;
};

export type CoachResponse = {
  status: string;
  task_id: string;
  task_type: string;
  result: unknown;
  session_id?: string;
};

export function postHeadCoach(body: MatchStrategyBody) {
  return apiPost<CoachResponse>("/coach/head-coach", body);
}

export function postCoachMatchChat(session_id: string, message: string) {
  return apiPost<{ status: string; session_id: string; reply: string }>("/coach/match-chat", {
    session_id,
    message,
  });
}

export function postRagQuery(question: string, verbose?: boolean) {
  return apiPost<{ status: string; question: string; answer: string }>("/rag/query", {
    question,
    verbose: verbose ?? false,
  });
}

export function postCoachDefense(body: MatchStrategyBody) {
  return apiPost<CoachResponse>("/coach/defense", body);
}

export function postCoachOffense(body: MatchStrategyBody) {
  return apiPost<CoachResponse>("/coach/offense", body);
}

export function postCoachSetPiece(body: MatchStrategyBody) {
  return apiPost<CoachResponse>("/coach/set-piece", body);
}

export function postCoachPositioning(body: MatchStrategyBody) {
  return apiPost<CoachResponse>("/coach/positioning", body);
}

export function postGenerateSimulations(match_id: number) {
  return apiPost<{ status: string; message: string }>(`/coach/generate-simulations/${match_id}`, {});
}

export function postGenerateCustomSimulations(
  match_id: number,
  body: {
    home_id: number;
    away_id: number;
    my_team_id: number;
    sim_type: string;
    count: number;
    coach_instruction?: string;
  }
) {
  return apiPost<{ status: string; message: string }>(`/coach/generate-custom-simulations/${match_id}`, body);
}

// ─── Taktik Simülasyonlar ──────────────────────────────────────────────────

export type SimulationMeta = {
  id: number;
  match_id: number;
  home_id?: number | null;
  away_id?: number | null;
  my_team_id?: number | null;
  home_name?: string | null;
  away_name?: string | null;
  sim_type: string;
  title: string | null;
  description: string | null;
  created_at: string | null;
};

export type SimulationDetail = SimulationMeta & {
  frames: Array<{
    timestamp: number;
    ball?: [number, number];
    ball_owner?: string | null;
    positions: Record<string, [number, number]>;
  }>;
};

export type SimGenerationStatus = {
  match_id: number;
  count: number;
  ready: boolean;
};

export type MatchAnalysisMeta = {
  id: number;
  match_id: number;
  home_id: number | null;
  away_id: number | null;
  my_team_id: number | null;
  home_name: string | null;
  away_name: string | null;
  match_date: string | null;
  session_id: string | null;
  task_id: string | null;
  created_at: string | null;
};

export type MatchAnalysisDetail = MatchAnalysisMeta & {
  result_text: string;
};

export const matchAnalysesApi = {
  list: (opts?: { match_id?: number; page?: number; page_size?: number }) =>
    apiGet<any>("/rest/match-analyses", { 
      match_id: opts?.match_id,
      page: opts?.page || 1,
      page_size: opts?.page_size || 20
    }),

  get: (id: number) => apiGet<MatchAnalysisDetail>(`/rest/match-analyses/${id}`),

  delete: (id: number) => apiDelete<{ status: string }>(`/rest/match-analyses/${id}`),
};

export const simulationsApi = {
  list: (matchId: number) =>
    apiGet<SimulationMeta[]>("/rest/simulations", { match_id: matchId }),

  get: (simId: number) =>
    apiGet<SimulationDetail>(`/rest/simulations/${simId}`),

  delete: (simId: number) =>
    apiDelete<{ status: string }>(`/rest/simulations/${simId}`),

  status: (matchId: number) =>
    apiGet<SimGenerationStatus>(`/rest/simulations/status/${matchId}`),
};
