import type {Metadata} from 'next';
import './globals.css';
export const metadata:Metadata={title:'PhoneUse Local | Open-source iPhone automation',description:'Control your USB-connected iPhone from a local web UI, API, or MCP client. Built by PhoneUse.'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>;}
