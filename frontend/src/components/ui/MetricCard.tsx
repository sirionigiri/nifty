import { Card, CardContent } from "@/components/ui/card"

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle: string;
  valueColor?: string; // e.g., "text-green-600", "text-red-600"
}

export function MetricCard({ title, value, subtitle, valueColor = "text-foreground" }: MetricCardProps) {
  return (
    <Card className="shadow-sm border-muted">
      <CardContent className="p-4 flex flex-col justify-between h-full">
        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
          {title}
        </p>
        <h3 className={`text-2xl font-bold ${valueColor}`}>
          {value}
        </h3>
        <p className="text-[11px] text-muted-foreground mt-1">
          {subtitle}
        </p>
      </CardContent>
    </Card>
  )
}