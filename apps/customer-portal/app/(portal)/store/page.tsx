"use client";

import { useEffect, useState } from "react";
import { ShoppingCart, Search, Star, Heart, Plus, Minus, Trash2 } from "lucide-react";
import brandConfig from "@/config/brand.json";

interface Product {
  id: string; sku: string; name: string; product_type: string;
  once_off_price: number; monthly_price: number; stock: number;
  specs: Record<string, string>; image_url?: string;
}

interface CartItem { product_id: string; name: string; price: number; quantity: number; type: string; }

export default function StorePage() {
  const [tab, setTab] = useState<"catalog" | "cart">("catalog");
  const [category, setCategory] = useState("all");
  const [products, setProducts] = useState<Product[]>([]);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    setProducts([
      { id: "1", sku: "RT-TP-AX55", name: "TP-Link Archer AX55", product_type: "hardware", once_off_price: 1299, monthly_price: 0, stock: 50, specs: { Speed: "AX3000", WiFi: "WiFi 6", Ports: "4" } },
      { id: "2", sku: "RT-TP-AX73", name: "TP-Link Archer AX73", product_type: "hardware", once_off_price: 1899, monthly_price: 0, stock: 30, specs: { Speed: "AX5400", WiFi: "WiFi 6", Ports: "4" } },
      { id: "3", sku: "ONT-NOKIA-G240G", name: "Nokia G-240G-A ONT", product_type: "hardware", once_off_price: 899, monthly_price: 0, stock: 200, specs: { Type: "GPON ONT", Ports: "4" } },
      { id: "4", sku: "MS-TP-DECO-X50", name: "TP-Link Deco X50 (3-pack)", product_type: "hardware", once_off_price: 3499, monthly_price: 0, stock: 20, specs: { Speed: "AX3000", Coverage: "500m²" } },
      { id: "5", sku: "VAS-STATIC-IP", name: "Static IP Address", product_type: "vas", once_off_price: 0, monthly_price: 99, stock: 999, specs: { Billing: "Monthly" } },
      { id: "6", sku: "VAS-ANTIVIRUS", name: "Norton 360 Security", product_type: "vas", once_off_price: 0, monthly_price: 69, stock: 999, specs: { Devices: "Up to 5" } },
    ]);
  }, []);

  const filtered = products.filter((p) => {
    if (category !== "all" && p.product_type !== category) return false;
    if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const addToCart = (product: Product) => {
    const price = product.product_type === "hardware" ? product.once_off_price : product.monthly_price;
    setCart((prev) => {
      const existing = prev.find((c) => c.product_id === product.id);
      if (existing) return prev.map((c) => c.product_id === product.id ? { ...c, quantity: c.quantity + 1 } : c);
      return [...prev, { product_id: product.id, name: product.name, price, quantity: 1, type: product.product_type }];
    });
  };

  const updateQty = (id: string, delta: number) => {
    setCart((prev) => prev.map((c) => c.product_id === id ? { ...c, quantity: Math.max(0, c.quantity + delta) } : c).filter((c) => c.quantity > 0));
  };

  const cartTotal = cart.reduce((s, c) => s + c.price * c.quantity, 0);

  return (
    <div className="p-4 lg:p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Store</h1>
          <p className="text-gray-500 mt-1">Hardware, accessories, and value-added services</p>
        </div>
        <button onClick={() => setTab(tab === "catalog" ? "cart" : "catalog")}
          className="relative p-2.5 rounded-xl border border-gray-200 hover:bg-gray-50">
          <ShoppingCart size={20} className="text-gray-600" />
          {cart.length > 0 && (
            <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full text-white text-[10px] font-bold flex items-center justify-center"
              style={{ backgroundColor: brandConfig.colors.primary }}>{cart.reduce((s, c) => s + c.quantity, 0)}</span>
          )}
        </button>
      </div>

      {tab === "catalog" ? (
        <>
          {/* Search + filter */}
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search products..."
                className="w-full pl-9 pr-3 py-2.5 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2" style={{ "--tw-ring-color": brandConfig.colors.primary } as React.CSSProperties} />
            </div>
          </div>

          <div className="flex gap-2 overflow-x-auto pb-1">
            {["all", "hardware", "vas", "accessory"].map((c) => (
              <button key={c} onClick={() => setCategory(c)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap capitalize ${category === c ? "text-white" : "bg-gray-100 text-gray-600"}`}
                style={category === c ? { backgroundColor: brandConfig.colors.primary } : undefined}>
                {c}
              </button>
            ))}
          </div>

          {/* Product grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {filtered.map((p) => (
              <div key={p.id} className="bg-white rounded-xl border border-gray-200 p-4 flex flex-col">
                <div className="flex-1">
                  <div className="flex items-start justify-between mb-2">
                    <span className="text-[10px] font-medium text-gray-400 uppercase">{p.product_type}</span>
                    <button className="p-1 rounded hover:bg-gray-100"><Heart size={14} className="text-gray-400" /></button>
                  </div>
                  <h3 className="text-sm font-semibold text-gray-900 mb-1">{p.name}</h3>
                  <p className="text-xs text-gray-500 mb-2">{p.sku}</p>
                  <div className="flex flex-wrap gap-1 mb-3">
                    {Object.entries(p.specs).slice(0, 3).map(([k, v]) => (
                      <span key={k} className="px-1.5 py-0.5 bg-gray-50 rounded text-[10px] text-gray-500">{k}: {v}</span>
                    ))}
                  </div>
                </div>
                <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                  <div>
                    {p.once_off_price > 0 && <p className="text-sm font-bold text-gray-900">R{p.once_off_price}</p>}
                    {p.monthly_price > 0 && <p className="text-sm font-bold text-gray-900">R{p.monthly_price}<span className="text-xs font-normal text-gray-400">/mo</span></p>}
                  </div>
                  <button onClick={() => addToCart(p)}
                    className="px-3 py-1.5 rounded-lg text-white text-xs font-medium flex items-center gap-1"
                    style={{ backgroundColor: brandConfig.colors.primary }}>
                    <Plus size={12} /> Add
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      ) : (
        /* Cart */
        <div className="space-y-4">
          {cart.length === 0 ? (
            <div className="text-center py-12">
              <ShoppingCart size={40} className="mx-auto text-gray-300 mb-3" />
              <p className="text-sm text-gray-500">Your cart is empty</p>
              <button onClick={() => setTab("catalog")} className="mt-3 text-sm font-medium" style={{ color: brandConfig.colors.primary }}>Browse Store</button>
            </div>
          ) : (
            <>
              <div className="space-y-2">
                {cart.map((item) => (
                  <div key={item.product_id} className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-3">
                    <div className="flex-1">
                      <p className="text-sm font-medium text-gray-900">{item.name}</p>
                      <p className="text-xs text-gray-500">{item.type === "hardware" ? `R${item.price}` : `R${item.price}/mo`}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => updateQty(item.product_id, -1)} className="p-1 rounded border border-gray-200 hover:bg-gray-50"><Minus size={12} /></button>
                      <span className="text-sm font-medium w-6 text-center">{item.quantity}</span>
                      <button onClick={() => updateQty(item.product_id, 1)} className="p-1 rounded border border-gray-200 hover:bg-gray-50"><Plus size={12} /></button>
                    </div>
                    <p className="text-sm font-semibold text-gray-900 w-20 text-right">R{(item.price * item.quantity).toFixed(0)}</p>
                    <button onClick={() => updateQty(item.product_id, -item.quantity)} className="p-1 text-gray-400 hover:text-red-500"><Trash2 size={14} /></button>
                  </div>
                ))}
              </div>
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <div className="flex justify-between mb-3">
                  <span className="text-sm text-gray-500">Total</span>
                  <span className="text-lg font-bold text-gray-900">R{cartTotal.toFixed(0)}</span>
                </div>
                <button className="w-full py-2.5 rounded-lg text-white text-sm font-medium" style={{ backgroundColor: brandConfig.colors.primary }}>
                  Checkout
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
