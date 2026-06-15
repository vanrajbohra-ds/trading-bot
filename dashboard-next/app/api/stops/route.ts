import { NextResponse } from 'next/server';
import { getStops } from '@/lib/github';

export async function GET() {
  try {
    const data = await getStops();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({}, { status: 200 });
  }
}
