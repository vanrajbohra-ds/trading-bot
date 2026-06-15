import { NextResponse } from 'next/server';
import { getOrders } from '@/lib/alpaca';

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const status = searchParams.get('status') ?? 'all';
  const limit  = parseInt(searchParams.get('limit') ?? '200', 10);
  try {
    const data = await getOrders(status, limit);
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
