const TOKEN = process.env.GITHUB_TOKEN ?? '';
const REPO  = process.env.GITHUB_REPO  ?? 'vanrajbohra-ds/trading-bot';
const API   = 'https://api.github.com';

const GH_HEADERS = {
  Authorization: `token ${TOKEN}`,
  Accept:        'application/vnd.github+json',
  'Content-Type': 'application/json',
};

export async function readFile(path: string): Promise<string | null> {
  try {
    const url = `${API}/repos/${REPO}/contents/${path}`;
    const res = await fetch(url, { headers: GH_HEADERS, next: { revalidate: 30 } });
    if (!res.ok) return null;
    const json = await res.json() as { content: string };
    return Buffer.from(json.content, 'base64').toString('utf-8');
  } catch {
    return null;
  }
}

export async function writeFile(
  path: string,
  content: string,
  message: string,
): Promise<boolean> {
  try {
    // Get current SHA
    const getUrl = `${API}/repos/${REPO}/contents/${path}`;
    const getRes = await fetch(getUrl, { headers: GH_HEADERS });
    if (!getRes.ok) return false;
    const { sha } = await getRes.json() as { sha: string };

    const putRes = await fetch(getUrl, {
      method: 'PUT',
      headers: GH_HEADERS,
      body: JSON.stringify({
        message,
        content: Buffer.from(content).toString('base64'),
        sha,
      }),
    });
    return putRes.ok;
  } catch {
    return false;
  }
}

export async function getWatchlist(): Promise<string[]> {
  const raw = await readFile('watchlist.json');
  if (!raw) return ['AAPL', 'TSLA', 'NVDA', 'MSFT', 'AMZN'];
  try { return JSON.parse(raw) as string[]; }
  catch { return ['AAPL', 'TSLA', 'NVDA', 'MSFT', 'AMZN']; }
}

export async function getStops(): Promise<Record<string, unknown>> {
  const raw = await readFile('positions_stops.json');
  if (!raw) return {};
  try { return JSON.parse(raw) as Record<string, unknown>; }
  catch { return {}; }
}
