export function formatTimestamp(timestamp?: string): string {
  if (!timestamp) {
    return "Not available";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "Not available";
  }

  return date.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function getElapsedSeconds(startedAt?: string, finishedAt?: string): number | undefined {
  if (!startedAt) {
    return undefined;
  }

  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();

  if (Number.isNaN(start) || Number.isNaN(end) || end < start) {
    return undefined;
  }

  return Math.floor((end - start) / 1000);
}

export function formatElapsedDuration(elapsedSeconds?: number): string {
  if (elapsedSeconds === undefined) {
    return "Starting...";
  }

  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = elapsedSeconds % 60;

  if (minutes === 0) {
    return `${seconds}s`;
  }

  return `${minutes}m ${seconds}s`;
}
