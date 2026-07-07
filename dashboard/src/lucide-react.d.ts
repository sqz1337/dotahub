declare module "lucide-react" {
  import type { SVGProps } from "react";

  export type LucideIcon = (props: SVGProps<SVGSVGElement>) => React.ReactElement;

  export const ChevronDown: LucideIcon;
  export const Crown: LucideIcon;
  export const Gauge: LucideIcon;
  export const Skull: LucideIcon;
  export const Zap: LucideIcon;
}
