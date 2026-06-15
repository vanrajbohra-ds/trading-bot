import { NextResponse } from 'next/server';
import { getWatchlist, writeFile } from '@/lib/github';

export async function GET() {
  try {
    const data = await getWatchlist();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

export async function PUT(req: Request) {
  try {
    const { watchlist } = await req.json() as { watchlist: string[] };
    const ok = await writeFile(
      'watchlist.json',
      JSON.stringify(watchlist, null, 2),
      `update watchlist: ${watchlist.join(', ')}`,
    );
    return NextResponse.json({ ok });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
