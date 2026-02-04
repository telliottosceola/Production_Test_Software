<script lang="ts">
  import { cn } from "$lib/utils";
  import ChevronDown from "lucide-svelte/icons/chevron-down";

  interface Option {
    value: string;
    label: string;
    disabled?: boolean;
  }

  interface Props {
    options: Option[];
    value?: string;
    placeholder?: string;
    disabled?: boolean;
    class?: string;
    onchange?: (value: string) => void;
  }

  let {
    options = [],
    value = $bindable(""),
    placeholder = "Select an option",
    disabled = false,
    class: className = "",
    onchange,
  }: Props = $props();

  function handleChange(e: Event) {
    const target = e.target as HTMLSelectElement;
    value = target.value;
    onchange?.(value);
  }
</script>

<div class={cn("relative", className)}>
  <select
    {disabled}
    {value}
    onchange={handleChange}
    class={cn(
      "flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 appearance-none pr-10",
      className
    )}
  >
    {#if placeholder}
      <option value="" disabled>{placeholder}</option>
    {/if}
    {#each options as option}
      <option value={option.value} disabled={option.disabled}>
        {option.label}
      </option>
    {/each}
  </select>
  <ChevronDown class="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 opacity-50 pointer-events-none" />
</div>
