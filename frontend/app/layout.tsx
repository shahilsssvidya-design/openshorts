import type { Metadata } from 'next';
import './globals.css';
export const metadata:Metadata={title:'OpenShorts — Make every moment count',description:'Turn long videos into beautiful vertical clips, with precise editing and animated captions.'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
