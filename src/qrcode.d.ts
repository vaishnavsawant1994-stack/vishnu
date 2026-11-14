declare module "qrcode" {
  export function toString(
    text: string,
    options?: {
      type?: "svg" | "utf8" | "terminal";
      margin?: number;
      color?: { dark?: string; light?: string };
    },
  ): Promise<string>;
}
