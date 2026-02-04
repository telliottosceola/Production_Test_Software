<script lang="ts">
  import "../app.css";
  
  let { children } = $props();
</script>

<div class="min-h-screen bg-background">
  {@render children()}
</div>
