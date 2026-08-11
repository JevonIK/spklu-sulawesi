"use strict";

const serviceState = document.getElementById("serviceState");

async function checkServiceHealth() {
    if (!serviceState) return;

    try {
        const response = await fetch("/api/health", {
            headers: { Accept: "application/json" },
        });
        const payload = await response.json();

        if (!response.ok || payload.status !== "ok") {
            throw new Error("Layanan belum siap");
        }

        serviceState.classList.add("is-ready");
        const nodeCount = payload.data?.dataset?.logical_nodes;
        serviceState.querySelector("span:last-child").textContent = nodeCount
            ? `Sistem siap · ${nodeCount} lokasi`
            : "Sistem siap";
    } catch (error) {
        serviceState.classList.add("is-error");
        serviceState.querySelector("span:last-child").textContent = "Sistem bermasalah";
    }
}

checkServiceHealth();
