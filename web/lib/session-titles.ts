"use client";

export function nextUntitledSessionTitle(
  existingTitles: Array<string | null | undefined>,
  baseTitle: string,
): string {
  const normalized = new Set(
    existingTitles
      .map((title) => (title || "").trim())
      .filter(Boolean),
  );

  if (!normalized.has(baseTitle)) {
    return baseTitle;
  }

  let index = 1;
  while (normalized.has(`${baseTitle}-${index}`)) {
    index += 1;
  }
  return `${baseTitle}-${index}`;
}
