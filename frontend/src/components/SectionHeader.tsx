import type { ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

export default function SectionHeader({ children }: Props) {
  return (
    <h2 className="text-sm font-bold uppercase tracking-widest text-text-dim mb-3 mt-8 first:mt-0">
      {children}
    </h2>
  );
}
