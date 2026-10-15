import "./globals.css";

export const metadata = {
  title: "JobPilot ID — Búsqueda laboral",
  description: "Perfiles Professional y Assistant con historial único de candidaturas",
  robots: "noindex, nofollow, noarchive",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
