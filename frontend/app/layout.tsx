import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata={title:'REPROVEX — The intelligent contract lab', description:'Adversarial testing, independent failure diagnosis, and bonded GenLayer consensus verification.'};
export default function Layout({children}:{children:React.ReactNode}) {return <html lang="en"><body>{children}</body></html>}
