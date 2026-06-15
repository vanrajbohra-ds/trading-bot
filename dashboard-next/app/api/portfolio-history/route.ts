import { NextResponse } from 'next/server';
import { getPortfolioHistory } from '@/lib/alpaca';

export async function GET() {
  try {
    const data = await getPortfolioHistory();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
