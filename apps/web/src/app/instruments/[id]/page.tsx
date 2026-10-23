"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { InstrumentView } from "@/components/InstrumentView";
import { Shell } from "@/components/Shell";

function Routed() {
  const { id } = useParams<{ id: string }>();
  return (
    <Shell>
      <InstrumentView id={id} />
    </Shell>
  );
}

export default function InstrumentPage() {
  return (
    <Suspense>
      <Routed />
    </Suspense>
  );
}
