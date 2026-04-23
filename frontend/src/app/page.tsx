import Link from "next/link";
import { ArrowRight, Database, LineChart, Video } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const tiles = [
  {
    title: "Veri & senkron",
    desc: "Lig, takım ve oyuncu listelerini güncelleyin ve sistem verilerini senkronize edin.",
    href: "/data",
    icon: Database,
  },
  {
    title: "Maç analizi",
    desc: "İki takım yan yana, düzenlenebilir istatistikler ve Head Coach API.",
    href: "/match-analysis",
    icon: LineChart,
  },
  {
    title: "Taktik simülasyon",
    desc: "Yapay zeka analizlerine dayalı dinamik taktik animasyonları oluşturun ve izleyin.",
    href: "/simulation",
    icon: Video,
  },
];

export default function HomePage() {
  return (
    <div className="space-y-10">
      <div className="space-y-3">
        <h1 className="text-3xl font-bold tracking-tight text-white">
          Football Tactical AI Assistant
        </h1>
        <p className="max-w-2xl text-sm text-[var(--muted-foreground)]">
          Maç verilerini analiz edin, yapay zeka destekli teknik direktör raporları oluşturun ve taktiksel varyasyonları simüle edin.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {tiles.map(({ title, desc, href, icon: Icon }) => (
          <Card
            key={href}
            className="group border-[var(--border)] bg-gradient-to-b from-[var(--card)] to-[#060d18]"
          >
            <CardHeader>
              <div className="flex items-center gap-2 text-cyan-400">
                <Icon className="h-5 w-5" />
                <CardTitle className="text-base">{title}</CardTitle>
              </div>
              <CardDescription className="text-xs leading-relaxed">{desc}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="secondary" size="sm" className="w-full gap-2">
                <Link href={href}>
                  Aç <ArrowRight className="h-3.5 w-3.5 opacity-70 transition group-hover:translate-x-0.5" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
