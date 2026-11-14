import { createFileRoute } from "@tanstack/react-router";
import { SignInPanel } from "@/components/vishnu/signin";

export const Route = createFileRoute("/login")({
  component: SignInPanel,
});
