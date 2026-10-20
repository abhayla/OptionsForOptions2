<!-- Adapted from abhayla/algochanakya@bf9faf7:frontend/src/App.vue (ADR-047): no auth bootstrap, no trading constants. -->
<script setup>
import { useRoute } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'

const route = useRoute()
</script>

<template>
  <!-- A public route (meta.public, GC-6 row LANDING) renders without the logged-in shell and nav. -->
  <router-view v-if="route.meta.public" />
  <AppLayout v-else>
    <router-view />
  </AppLayout>
</template>
