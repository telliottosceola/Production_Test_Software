<script lang="ts">
  import { onMount } from "svelte";
  import { Button } from "$lib/components/ui/button";
  import { Select } from "$lib/components/ui/select";
  import * as Card from "$lib/components/ui/card";
  // ScrollArea removed - using native scrollable div for auto-scroll support
  import RefreshCw from "lucide-svelte/icons/refresh-cw";
  import Usb from "lucide-svelte/icons/usb";
  import Play from "lucide-svelte/icons/play";
  import RotateCcw from "lucide-svelte/icons/rotate-ccw";
  import Trash2 from "lucide-svelte/icons/trash-2";
  import FlaskConical from "lucide-svelte/icons/flask-conical";
  import CheckCircle from "lucide-svelte/icons/check-circle";
  import XCircle from "lucide-svelte/icons/x-circle";
  import Loader2 from "lucide-svelte/icons/loader-2";
  import AlertTriangle from "lucide-svelte/icons/alert-triangle";
  import {
    listSerialPorts,
    flashFirmware,
    runDeviceTest,
    factoryReset,
    eraseDevice,
    onFlashOutput,
    onTestOutput,
    onResetOutput,
    onEraseOutput,
    FIRMWARE_OPTIONS,
    type SerialPortInfo,
  } from "$lib/tauri";
  
  // Check if running in Tauri (v2 uses __TAURI_INTERNALS__)
  const isTauri = typeof window !== "undefined" && ("__TAURI_INTERNALS__" in window || "__TAURI__" in window);

  // State
  let serialPorts = $state<SerialPortInfo[]>([]);
  let selectedPort = $state("");
  let selectedFirmware = $state("23");
  let isLoading = $state(false);
  let isRefreshing = $state(false);
  let currentOperation = $state<"idle" | "programming" | "testing" | "resetting" | "erasing">("idle");
  let logContainer: HTMLDivElement;
  let outputLog = $state<string[]>([]);
  let statusMessage = $state("");
  let statusType = $state<"idle" | "success" | "error" | "loading">("idle");
  let showEraseConfirm = $state(false);

  // Computed
  let portOptions = $derived(
    serialPorts.map((p) => ({
      value: p.name,
      label: `${p.name} (${p.port_type})`,
    }))
  );

  let firmwareOptions = $derived(
    FIRMWARE_OPTIONS.map((f) => ({
      value: f.id.toString(),
      label: f.name,
    }))
  );

  let canPerformAction = $derived(
    isTauri && selectedPort !== "" && selectedFirmware !== "" && currentOperation === "idle"
  );

  // Functions
  function addLog(message: string) {
    const timestamp = new Date().toLocaleTimeString();
    outputLog = [...outputLog, `[${timestamp}] ${message}`];
    // Auto-scroll to bottom after adding log
    setTimeout(() => {
      if (logContainer) {
        logContainer.scrollTop = logContainer.scrollHeight;
      }
    }, 0);
  }

  function clearLog() {
    outputLog = [];
  }

  function setStatus(message: string, type: "idle" | "success" | "error" | "loading") {
    statusMessage = message;
    statusType = type;
  }

  async function refreshPorts() {
    isRefreshing = true;
    try {
      serialPorts = await listSerialPorts();
      if (serialPorts.length === 0) {
        addLog("No serial ports found");
      } else {
        addLog(`Found ${serialPorts.length} serial port(s)`);
      }
    } catch (error) {
      addLog(`Error listing ports: ${error}`);
      setStatus("Failed to list serial ports", "error");
    } finally {
      isRefreshing = false;
    }
  }

  async function handleProgram() {
    if (!canPerformAction) return;

    currentOperation = "programming";
    isLoading = true;
    clearLog();
    setStatus("Programming device...", "loading");

    const firmwareName = FIRMWARE_OPTIONS.find(
      (f) => f.id.toString() === selectedFirmware
    )?.name;
    addLog(`Starting firmware flash: ${firmwareName}`);
    addLog(`Port: ${selectedPort}`);
    addLog(`Firmware ID: ${selectedFirmware}`);
    addLog("---");

    // Set up real-time output listener
    let unlisten: (() => void) | null = null;
    try {
      unlisten = await onFlashOutput((line) => {
        if (line.trim()) {
          addLog(line);
        }
      });
    } catch (e) {
      // Event listener failed, will fall back to final output
    }

    try {
      const result = await flashFirmware(selectedPort, parseInt(selectedFirmware));

      // Clean up listener
      if (unlisten) unlisten();

      addLog("---");
      if (result.success) {
        setStatus("Firmware programmed successfully!", "success");
        addLog("SUCCESS: Firmware flash completed");
      } else {
        setStatus("Firmware programming failed", "error");
        addLog("FAILED: " + result.message);
      }
    } catch (error) {
      if (unlisten) unlisten();
      setStatus("Programming error", "error");
      addLog(`ERROR: ${error}`);
    } finally {
      currentOperation = "idle";
      isLoading = false;
    }
  }

  async function handleTest() {
    if (!canPerformAction) return;

    currentOperation = "testing";
    isLoading = true;
    clearLog();
    setStatus("Running device test...", "loading");

    addLog(`Starting production test on ${selectedPort}`);
    addLog("Sending TEST command...");
    addLog("---");

    // Set up real-time output listener
    let unlisten: (() => void) | null = null;
    try {
      unlisten = await onTestOutput((line) => {
        if (line.trim()) {
          addLog(line);
        }
      });
    } catch (e) {
      // Event listener failed, will fall back to final output
    }

    try {
      const result = await runDeviceTest(selectedPort);

      // Clean up listener
      if (unlisten) unlisten();

      addLog("---");

      if (result.success) {
        setStatus("All tests passed!", "success");
        addLog("TEST RESULT: PASS");
        if (result.firmware_version) {
          addLog(`Firmware: ${result.firmware_version}`);
        }
        if (result.mac_address) {
          addLog(`MAC: ${result.mac_address}`);
        }
      } else {
        setStatus(`Test failed: ${result.message}`, "error");
        addLog(`TEST RESULT: FAIL - ${result.message}`);
      }
    } catch (error) {
      if (unlisten) unlisten();
      setStatus("Test error", "error");
      addLog(`ERROR: ${error}`);
    } finally {
      currentOperation = "idle";
      isLoading = false;
    }
  }

  async function handleFactoryReset() {
    if (!canPerformAction) return;

    currentOperation = "resetting";
    isLoading = true;
    clearLog();
    setStatus("Performing factory reset...", "loading");

    addLog(`Sending FACTORY_RESET to ${selectedPort}`);
    addLog("---");

    // Set up real-time output listener
    let unlisten: (() => void) | null = null;
    try {
      unlisten = await onResetOutput((line) => {
        if (line.trim()) {
          addLog(line);
        }
      });
    } catch (e) {
      // Event listener failed, will fall back to final output
    }

    try {
      const result = await factoryReset(selectedPort);

      // Clean up listener
      if (unlisten) unlisten();

      addLog("---");

      if (result.success) {
        setStatus("Factory reset completed!", "success");
        addLog("SUCCESS: Device has been factory reset");
      } else {
        setStatus("Factory reset failed", "error");
        addLog("FAILED: " + result.message);
      }
    } catch (error) {
      if (unlisten) unlisten();
      setStatus("Reset error", "error");
      addLog(`ERROR: ${error}`);
    } finally {
      currentOperation = "idle";
      isLoading = false;
    }
  }

  function handleErase() {
    if (!canPerformAction) return;
    // Show confirmation dialog
    showEraseConfirm = true;
  }

  function cancelErase() {
    showEraseConfirm = false;
  }

  async function confirmErase() {
    showEraseConfirm = false;
    
    currentOperation = "erasing";
    isLoading = true;
    clearLog();
    setStatus("Erasing device flash...", "loading");

    addLog(`Erasing flash on ${selectedPort}`);
    addLog("---");

    // Set up real-time output listener
    let unlisten: (() => void) | null = null;
    try {
      unlisten = await onEraseOutput((line) => {
        if (line.trim()) {
          addLog(line);
        }
      });
    } catch (e) {
      // Event listener failed, will fall back to final output
    }

    try {
      const result = await eraseDevice(selectedPort);

      // Clean up listener
      if (unlisten) unlisten();

      addLog("---");

      if (result.success) {
        setStatus("Flash erased successfully!", "success");
        addLog("SUCCESS: Device flash has been erased");
      } else {
        setStatus("Flash erase failed", "error");
        addLog("FAILED: " + result.message);
      }
    } catch (error) {
      if (unlisten) unlisten();
      setStatus("Erase error", "error");
      addLog(`ERROR: ${error}`);
    } finally {
      currentOperation = "idle";
      isLoading = false;
    }
  }

  onMount(() => {
    if (isTauri) {
      refreshPorts();
    } else {
      addLog("Running in browser mode - Tauri API not available");
      addLog("Run 'npm run tauri dev' to test with full functionality");
      setStatus("Browser mode - limited functionality", "idle");
    }
  });
</script>

<div class="container mx-auto p-6 max-w-3xl">
  <Card.Root>
    <Card.Header class="pb-4">
      <Card.Title class="flex items-center gap-2">
        <Usb class="h-6 w-6" />
        NCD Sensor Programmer
      </Card.Title>
    </Card.Header>

    <Card.Content class="space-y-6">
      <!-- Browser Mode Warning -->
      {#if !isTauri}
        <div class="flex items-center gap-2 p-3 rounded-md bg-amber-100 text-amber-800">
          <AlertTriangle class="h-5 w-5 flex-shrink-0" />
          <div>
            <span class="font-medium">Browser Mode</span>
            <span class="text-sm"> - Run <code class="bg-amber-200 px-1 rounded">npm run tauri dev</code> for full functionality</span>
          </div>
        </div>
      {/if}

      <!-- Serial Port Selection -->
      <div class="space-y-2">
        <span class="text-sm font-medium">Serial Port</span>
        <div class="flex gap-2">
          <Select
            options={portOptions}
            bind:value={selectedPort}
            placeholder="Select a serial port"
            disabled={currentOperation !== "idle" || !isTauri}
            class="flex-1"
          />
          <Button
            variant="outline"
            size="icon"
            onclick={refreshPorts}
            disabled={isRefreshing || currentOperation !== "idle" || !isTauri}
          >
            <RefreshCw class={isRefreshing ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
          </Button>
        </div>
      </div>

      <!-- Firmware Selection -->
      <div class="space-y-2">
        <span class="text-sm font-medium">Firmware</span>
        <Select
          options={firmwareOptions}
          bind:value={selectedFirmware}
          placeholder="Select firmware"
          disabled={currentOperation !== "idle" || !isTauri}
        />
      </div>

      <!-- Action Buttons - Row 1 -->
      <div class="flex gap-3">
        <Button
          onclick={handleProgram}
          disabled={!canPerformAction}
          class="flex-1"
        >
          {#if currentOperation === "programming"}
            <Loader2 class="mr-2 h-4 w-4 animate-spin" />
            Programming...
          {:else}
            <Play class="mr-2 h-4 w-4" />
            Program
          {/if}
        </Button>

        <Button
          variant="secondary"
          onclick={handleTest}
          disabled={!canPerformAction}
          class="flex-1"
        >
          {#if currentOperation === "testing"}
            <Loader2 class="mr-2 h-4 w-4 animate-spin" />
            Testing...
          {:else}
            <FlaskConical class="mr-2 h-4 w-4" />
            Test
          {/if}
        </Button>
      </div>

      <!-- Action Buttons - Row 2 -->
      <div class="flex gap-3">
        <Button
          variant="outline"
          onclick={handleErase}
          disabled={!canPerformAction}
          class="flex-1"
        >
          {#if currentOperation === "erasing"}
            <Loader2 class="mr-2 h-4 w-4 animate-spin" />
            Erasing...
          {:else}
            <Trash2 class="mr-2 h-4 w-4" />
            Erase Flash
          {/if}
        </Button>

        <Button
          variant="destructive"
          onclick={handleFactoryReset}
          disabled={!canPerformAction}
          class="flex-1"
        >
          {#if currentOperation === "resetting"}
            <Loader2 class="mr-2 h-4 w-4 animate-spin" />
            Resetting...
          {:else}
            <RotateCcw class="mr-2 h-4 w-4" />
            Factory Reset
          {/if}
        </Button>
      </div>

      <!-- Output Log -->
      <div class="space-y-2">
        <div class="flex items-center justify-between">
          <label class="text-sm font-medium">Output Log</label>
          <Button variant="ghost" size="sm" onclick={clearLog} disabled={outputLog.length === 0}>
            Clear
          </Button>
        </div>
        <div 
          bind:this={logContainer}
          class="h-64 rounded-md border bg-muted/50 overflow-y-auto"
        >
          <div class="p-4 font-mono text-xs space-y-1">
            {#if outputLog.length === 0}
              <p class="text-muted-foreground italic">No output yet. Select a port and perform an action.</p>
            {:else}
              {#each outputLog as line}
                <p
                  class={line.includes("SUCCESS") || line.includes("PASS") || line.includes("[CHECK] ✓")
                    ? "text-green-600"
                    : line.includes("ERROR") || line.includes("FAIL") || line.includes("[CHECK] ✗")
                      ? "text-red-600"
                      : line.includes("[PROGRESS]") || line.includes("[INFO]")
                        ? "text-blue-600"
                        : line.startsWith("---")
                          ? "text-muted-foreground"
                          : ""}
                >
                  {line}
                </p>
              {/each}
            {/if}
          </div>
        </div>
      </div>

      <!-- Status Bar -->
      {#if statusMessage}
        <div
          class={`flex items-center gap-2 p-3 rounded-md ${
            statusType === "success"
              ? "bg-green-100 text-green-800"
              : statusType === "error"
                ? "bg-red-100 text-red-800"
                : statusType === "loading"
                  ? "bg-blue-100 text-blue-800"
                  : "bg-muted text-muted-foreground"
          }`}
        >
          {#if statusType === "success"}
            <CheckCircle class="h-5 w-5" />
          {:else if statusType === "error"}
            <XCircle class="h-5 w-5" />
          {:else if statusType === "loading"}
            <Loader2 class="h-5 w-5 animate-spin" />
          {/if}
          <span class="font-medium">{statusMessage}</span>
        </div>
      {/if}
    </Card.Content>
  </Card.Root>

  <p class="text-center text-xs text-muted-foreground mt-4">
    NCD Sensor Programmer v0.1.0
  </p>
</div>

<!-- Erase Confirmation Dialog -->
{#if showEraseConfirm}
  <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
    <div class="bg-white rounded-lg shadow-xl p-6 max-w-md mx-4">
      <div class="flex items-center gap-3 mb-4">
        <div class="flex-shrink-0 w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
          <AlertTriangle class="h-6 w-6 text-red-600" />
        </div>
        <h3 class="text-lg font-semibold text-gray-900">Erase Device Flash?</h3>
      </div>
      <p class="text-gray-600 mb-6">
        This will completely erase all firmware and data from the device. This action cannot be undone.
      </p>
      <div class="flex gap-3 justify-end">
        <Button variant="outline" onclick={cancelErase}>
          No, Cancel
        </Button>
        <Button variant="destructive" onclick={confirmErase}>
          Yes, Erase
        </Button>
      </div>
    </div>
  </div>
{/if}
