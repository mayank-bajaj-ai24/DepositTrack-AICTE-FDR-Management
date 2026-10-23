"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Shell } from "@/components/Shell";
import { homeFor, useAuth } from "@/lib/auth";

export default function Home() {
  const auth = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (auth.ready && auth.user) router.replace(homeFor(auth.roles));
  }, [auth.ready, auth.user, auth.roles, router]);
  return <Shell>{null}</Shell>;
}
