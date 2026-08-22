import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

const Icon = ({ size = 18, children, ...props }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
    {children}
  </svg>
);

export const PinIcon = (props: IconProps) => <Icon {...props}><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/></Icon>;
export const SparkIcon = (props: IconProps) => <Icon {...props}><path d="m12 3 1.2 4.2a5 5 0 0 0 3.5 3.5L21 12l-4.3 1.3a5 5 0 0 0-3.5 3.5L12 21l-1.2-4.2a5 5 0 0 0-3.5-3.5L3 12l4.3-1.3a5 5 0 0 0 3.5-3.5L12 3Z"/></Icon>;
export const ArrowIcon = (props: IconProps) => <Icon {...props}><path d="M5 12h14m-5-5 5 5-5 5"/></Icon>;
export const TrashIcon = (props: IconProps) => <Icon {...props}><path d="M4 7h16M9 7V4h6v3m3 0-1 14H7L6 7m4 4v6m4-6v6"/></Icon>;
export const CheckIcon = (props: IconProps) => <Icon {...props}><path d="m5 12 4 4L19 6"/></Icon>;
export const AlertIcon = (props: IconProps) => <Icon {...props}><path d="M10.3 3.8 2.7 17a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 3.8a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4m0 3h.01"/></Icon>;
export const CloseIcon = (props: IconProps) => <Icon {...props}><circle cx="12" cy="12" r="9"/><path d="m9 9 6 6m0-6-6 6"/></Icon>;
export const CopyIcon = (props: IconProps) => <Icon {...props}><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3"/></Icon>;
export const EditIcon = (props: IconProps) => <Icon {...props}><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/></Icon>;
export const ShieldIcon = (props: IconProps) => <Icon {...props}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/></Icon>;
export const ChevronIcon = (props: IconProps) => <Icon {...props}><path d="m9 18 6-6-6-6"/></Icon>;
export const RefreshIcon = (props: IconProps) => <Icon {...props}><path d="M20 6v5h-5M4 18v-5h5"/><path d="M18.5 9A7 7 0 0 0 6 6.5L4 11m16 2-2 4.5A7 7 0 0 1 5.5 15"/></Icon>;
