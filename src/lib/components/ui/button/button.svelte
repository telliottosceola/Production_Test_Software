<script lang="ts">
  import { cn } from "$lib/utils";
  import { buttonVariants, type Variant, type Size } from "./index";

  interface Props {
    variant?: Variant;
    size?: Size;
    class?: string;
    disabled?: boolean;
    type?: "button" | "submit" | "reset";
    onclick?: (e: MouseEvent) => void;
    children?: import('svelte').Snippet;
  }

  let {
    variant = "default",
    size = "default",
    class: className = "",
    disabled = false,
    type = "button",
    onclick,
    children,
  }: Props = $props();
</script>

<button
  {type}
  {disabled}
  class={cn(buttonVariants({ variant, size }), className)}
  onclick={onclick}
>
  {@render children?.()}
</button>
