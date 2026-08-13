import type {
  ExperimentAnalysis,
  FunnelStep,
  MarketplaceOverview,
  SegmentRow,
  SegmentType,
  SqlQuery,
  TimeseriesPoint,
} from "@/types/experiment";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8010";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function get<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { cache: "no-store" });
  } catch {
    throw new ApiError(
      "The analytics API is unreachable. Start it with `uvicorn api.main:app --port 8010`.",
      0,
    );
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    let code: string | undefined;
    try {
      const body = (await response.json()) as { detail?: string; code?: string };
      if (body.detail) detail = body.detail;
      code = body.code;
    } catch {
      /* keep default */
    }
    throw new ApiError(detail, response.status, code);
  }
  return (await response.json()) as T;
}

export const api = {
  analysis: (id = "EXP-024") => get<ExperimentAnalysis>(`/experiments/${id}/analysis`),
  timeseries: (id = "EXP-024") => get<TimeseriesPoint[]>(`/experiments/${id}/timeseries`),
  segments: (type: SegmentType, id = "EXP-024") =>
    get<{ segment_type: SegmentType; rows: SegmentRow[] }>(
      `/experiments/${id}/segments?segment_type=${type}&limit=20`,
    ),
  funnel: (id = "EXP-024") => get<FunnelStep[]>(`/experiments/${id}/funnel`),
  marketplace: (id = "EXP-024") =>
    get<MarketplaceOverview>(`/experiments/${id}/marketplace`),
  sql: () => get<SqlQuery[]>("/experiments/sql"),
};
