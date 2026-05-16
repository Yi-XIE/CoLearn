export type VersionSource = "git" | "env" | "unknown";

export interface ParsedBuild {
  tag: string | null;
  isDev: boolean;
  isDirty: boolean;
  display: string;
  raw: string;
  commitsAhead: number | null;
  commit: string | null;
}

const SEMVER_TAG = String.raw`(\d+\.\d+\.\d+(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?)`;
const DIRTY_SUFFIX = "-dev";
const DIRTY_DISPLAY = "\u00b7dev";

export function parseBuild(
  rawValue: string | null | undefined,
): ParsedBuild | null {
  const raw = rawValue?.trim() ?? "";
  if (!raw) return null;

  const isDirty = raw.endsWith(DIRTY_SUFFIX);
  const stripped = isDirty ? raw.slice(0, -DIRTY_SUFFIX.length) : raw;

  const ahead = stripped.match(
    new RegExp(`^v?${SEMVER_TAG}-(\\d+)-g([0-9a-f]+)$`),
  );
  if (ahead) {
    const tag = `v${ahead[1]}`;
    const commitsAhead = Number.parseInt(ahead[2], 10);
    const commit = ahead[3];
    return {
      tag,
      isDev: true,
      isDirty,
      display: `${tag}+${commitsAhead}${isDirty ? DIRTY_DISPLAY : ""}`,
      raw,
      commitsAhead,
      commit,
    };
  }

  const cleanTag = stripped.match(new RegExp(`^v?${SEMVER_TAG}$`));
  if (cleanTag) {
    const tag = `v${cleanTag[1]}`;
    return {
      tag,
      isDev: isDirty,
      isDirty,
      display: isDirty ? `${tag}${DIRTY_DISPLAY}` : tag,
      raw,
      commitsAhead: null,
      commit: null,
    };
  }

  return {
    tag: null,
    isDev: true,
    isDirty,
    display: "dev",
    raw,
    commitsAhead: null,
    commit: null,
  };
}

export function normalizeVersionTag(
  raw: string | null | undefined,
): string | null {
  const parsed = parseBuild(raw);
  return parsed && !parsed.isDev ? parsed.tag : null;
}

export function unknownBuild(raw = ""): ParsedBuild {
  return {
    tag: null,
    isDev: true,
    isDirty: false,
    display: raw.trim() || "unknown",
    raw: raw.trim(),
    commitsAhead: null,
    commit: null,
  };
}
