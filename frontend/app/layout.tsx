import './globals.css';
import type { Metadata } from 'next';
export const metadata: Metadata = { title: 'Tracepoint | Digital Evidence', description: 'Digital evidence acquisition and integrity verification console' };
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="en"><body>{children}</body></html>; }
