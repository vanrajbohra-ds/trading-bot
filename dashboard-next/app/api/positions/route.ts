import { NextResponse } from 'next/server';
import { getPositions } from '@/lib/alpaca';

export async function GET() {
  try {
    const data = await getPositions();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
