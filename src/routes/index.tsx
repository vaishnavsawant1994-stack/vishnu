import { createFileRoute } from "@tanstack/react-router";
import { VishnuApp } from "@/components/vishnu/app";

export const Route = createFileRoute("/")({
  component: VishnuApp,
});
