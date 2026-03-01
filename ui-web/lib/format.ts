export function toUsd(value: number): string {
  return `$${value.toFixed(6)}`;
}

export function toLocalTimestamp(isoTimestamp: string): string {
  const parsedDate = new Date(isoTimestamp);
  if (Number.isNaN(parsedDate.getTime())) {
    return isoTimestamp;
  }
  return parsedDate.toLocaleString();
}
