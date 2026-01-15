// FibreHub White-label Portal Logic
document.addEventListener('DOMContentLoaded', async () => {
    // 1. Load Theme Configuration
    const loadTheme = async () => {
        try {
            // In a real app, this would be a fetch to the backend
            // for now we'll simulate loading from the brand_guidelines folder
            // or use a default if it fails
            const response = await fetch('../brand_guidelines/default_theme.json');
            const theme = await response.json();
            applyTheme(theme);
        } catch (err) {
            console.warn("Could not load theme config, using defaults:", err);
            // Default FibreHub Red Theme
            applyTheme({
                brand_name: "FibreHub Portal",
                primary_color: "#e31b23",
                accent_color: "#22d3ee",
                hero: {
                    title: "Ultrafast Prepaid Fibre.",
                    subtitle: "Get blazing-fast fibre while controlling your spend."
                }
            });
        }
    };

    const applyTheme = (theme) => {
        document.documentElement.style.setProperty('--primary', theme.primary_color);
        document.documentElement.style.setProperty('--accent', theme.accent_color);

        // Convert hex to RGB for overlays
        const r = parseInt(theme.primary_color.slice(1, 3), 16);
        const g = parseInt(theme.primary_color.slice(3, 5), 16);
        const b = parseInt(theme.primary_color.slice(5, 7), 16);
        document.documentElement.style.setProperty('--primary-rgb', `${r}, ${g}, ${b}`);

        document.getElementById('brand-name').textContent = theme.brand_name;
        document.getElementById('footer-brand-name').textContent = theme.brand_name;
        document.getElementById('hero-title').innerHTML = theme.hero.title.replace("Fibre", '<span class="gradient-text">Fibre</span>');
        document.getElementById('hero-subtitle').textContent = theme.hero.subtitle;
        document.title = `${theme.brand_name} | Powered by FibreHub`;
    };

    // 2. Mock Packages Data
    const packages = [
        { id: 1, name: "Starter Fibre", price: "399", speed: "25/25", type: "monthly", popular: false },
        { id: 2, name: "Pro Fibre", price: "699", speed: "100/100", type: "monthly", popular: true },
        { id: 3, name: "Gamer Fibre", price: "999", speed: "200/200", type: "monthly", popular: false },
        { id: 4, name: "Prepaid 7-Day", price: "99", speed: "50/50", type: "prepaid", popular: false },
        { id: 5, name: "Prepaid 30-Day", price: "299", speed: "50/50", type: "prepaid", popular: true }
    ];

    // 3. UI Interactions
    const browseBtn = document.getElementById('browse-packages-btn');
    const coverageBtn = document.getElementById('check-coverage-btn');
    const packagesSection = document.getElementById('packages');
    const packagesContainer = document.getElementById('packages-container');
    const addressInput = document.getElementById('address-search');

    const showPackages = (filter = 'monthly') => {
        packagesSection.classList.remove('hidden');
        packagesSection.scrollIntoView({ behavior: 'smooth' });

        const filtered = packages.filter(p => p.type === filter);
        packagesContainer.innerHTML = filtered.map(p => `
            <div class="package-card ${p.popular ? 'popular' : ''}">
                <h3>${p.name}</h3>
                <p class="speed">${p.speed} Mbps Uncapped</p>
                <div class="price">R${p.price}<span>/pm</span></div>
                <ul class="package-features">
                    <li><i class="fas fa-check"></i> Free Installation</li>
                    <li><i class="fas fa-check"></i> Free Router</li>
                    <li><i class="fas fa-check"></i> No Contract</li>
                </ul>
                <button class="btn btn-primary" onclick="alert('Proceeding to sign-up for ${p.name}')">SELECT PACKAGE</button>
            </div>
        `).join('');
    };

    browseBtn.addEventListener('click', () => showPackages('monthly'));

    coverageBtn.addEventListener('click', () => {
        if (!addressInput.value) {
            alert("Please enter your address first.");
            addressInput.focus();
            return;
        }
        alert(`Checking coverage for: ${addressInput.value}...`);
        setTimeout(() => {
            alert("Great news! You have Full Fibre coverage.");
            showPackages('monthly');
        }, 1500);
    });

    // Tab switching for packages
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            showPackages(btn.dataset.type);
        });
    });

    // Initialize
    await loadTheme();
});
