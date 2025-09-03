import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from matplotlib.gridspec import GridSpec

# Set style
plt.style.use("seaborn-v0_8")
sns.set_palette("husl")

# Read the parquet file
df = pd.read_parquet("data/processed/2021_station_hour_processed.parquet")

# Create figure with subplots
fig = plt.figure(figsize=(20, 16))
gs = GridSpec(3, 2, figure=fig, hspace=0.3, wspace=0.3)

# 1. 24小時交通流量熱力圖 (按月份)
ax1 = fig.add_subplot(gs[0, 0])
# Create pivot table for heatmap
hourly_monthly_flow = df.pivot_table(
    values="median_flow", index="hour", columns="month", aggfunc="mean"
)
# Reorder months
month_order = ["January", "February", "March", "April", "May", "June", "July", "August"]
hourly_monthly_flow = hourly_monthly_flow[month_order]

sns.heatmap(
    hourly_monthly_flow, cmap="YlOrRd", ax=ax1, cbar_kws={"label": "平均流量 (輛/小時)"}
)
ax1.set_title("24小時交通流量熱力圖 (按月份)", fontsize=14, fontweight="bold")
ax1.set_xlabel("月份")
ax1.set_ylabel("小時")

# 2. 主要路線平均車速比較 (箱形圖)
ax2 = fig.add_subplot(gs[0, 1])
# Get top 5 routes by data count
top_routes = df["route"].value_counts().head(5).index
route_data = df[df["route"].isin(top_routes)]

sns.boxplot(data=route_data, x="route", y="median_speed", ax=ax2, showfliers=False)
ax2.set_title("主要路線平均車速分布", fontsize=14, fontweight="bold")
ax2.set_xlabel("路線編號")
ax2.set_ylabel("中位數車速 (mph)")
ax2.set_ylim(0, 80)

# 3. 流量 vs 車速散點圖 (按車道數)
ax3 = fig.add_subplot(gs[1, 0])
# Sample data for better visualization (every 10th point)
sample_df = df.iloc[::10, :]

scatter = ax3.scatter(
    sample_df["median_flow"],
    sample_df["median_speed"],
    c=sample_df["lanes"],
    cmap="viridis",
    alpha=0.6,
    s=20,
)
ax3.set_title("流量 vs 車速關係 (按車道數)", fontsize=14, fontweight="bold")
ax3.set_xlabel("中位數流量 (輛/小時)")
ax3.set_ylabel("中位數車速 (mph)")
ax3.set_xlim(0, 12000)
ax3.set_ylim(0, 80)
plt.colorbar(scatter, ax=ax3, label="車道數")

# 4. 各方向高峰時段流量變化 (折線圖)
ax4 = fig.add_subplot(gs[1, 1])
# Calculate average flow by hour and direction
hourly_dir_flow = df.groupby(["hour", "direction"])["median_flow"].mean().reset_index()

for direction in ["N", "S", "E", "W"]:
    dir_data = hourly_dir_flow[hourly_dir_flow["direction"] == direction]
    if not dir_data.empty:
        ax4.plot(
            dir_data["hour"],
            dir_data["median_flow"],
            label=f"{direction}向",
            linewidth=2,
            marker="o",
            markersize=4,
        )

ax4.set_title("各方向24小時流量變化", fontsize=14, fontweight="bold")
ax4.set_xlabel("小時")
ax4.set_ylabel("平均流量 (輛/小時)")
ax4.legend(title="行車方向")
ax4.grid(True, alpha=0.3)
ax4.set_xlim(0, 23)

# 5. 佔有率分布直方圖 (按車道類型)
ax5 = fig.add_subplot(gs[2, :])
# Create separate histograms for ML and HV
ml_data = df[df["type"] == "ML"]["median_occup"]
hv_data = df[df["type"] == "HV"]["median_occup"]

ax5.hist(ml_data, bins=50, alpha=0.7, label="主要車道 (ML)", density=True)
ax5.hist(hv_data, bins=50, alpha=0.7, label="高乘載車道 (HV)", density=True)

ax5.set_title("道路佔有率分布 (按車道類型)", fontsize=14, fontweight="bold")
ax5.set_xlabel("中位數佔有率")
ax5.set_ylabel("密度")
ax5.legend()
ax5.set_xlim(0, 0.6)

# Add main title
fig.suptitle(
    "CalTrans 第12區交通狀況分析 - 2021年", fontsize=18, fontweight="bold", y=0.98
)

# Add summary statistics as text
stats_text = f"""
資料摘要：
• 總測站數：{df['station'].nunique()} 個
• 資料期間：2021年1月-8月
• 平均流量：{df['median_flow'].mean():.0f} 輛/小時
• 平均車速：{df['median_speed'].mean():.1f} mph
• 主要路線：{', '.join(map(str, top_routes.tolist()))}
"""
fig.text(
    0.02,
    0.02,
    stats_text,
    fontsize=10,
    verticalalignment="bottom",
    bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8),
)

plt.tight_layout()
plt.savefig("traffic_analysis_dashboard.png", dpi=300, bbox_inches="pad_inches=0.5")
plt.show()

# Additional detailed analysis plots

# Plot 6: Monthly Traffic Trends by Route Type
fig2, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

# Monthly flow trends
monthly_flow = df.groupby("month")["median_flow"].mean().reset_index()
month_order = ["January", "February", "March", "April", "May", "June", "July", "August"]
monthly_flow["month"] = pd.Categorical(
    monthly_flow["month"], categories=month_order, ordered=True
)
monthly_flow = monthly_flow.sort_values("month")

ax1.plot(
    monthly_flow["month"],
    monthly_flow["median_flow"],
    marker="o",
    linewidth=2,
    markersize=8,
    color="#2E86AB",
)
ax1.set_title("2021年月度流量趨勢", fontsize=14, fontweight="bold")
ax1.set_xlabel("月份")
ax1.set_ylabel("平均流量 (輛/小時)")
ax1.tick_params(axis="x", rotation=45)
ax1.grid(True, alpha=0.3)

# Peak vs Off-peak comparison
df["peak_hour"] = df["hour"].apply(
    lambda x: "Peak (7-9, 16-18)" if (7 <= x <= 9) or (16 <= x <= 18) else "Off-peak"
)
peak_comparison = df.groupby("peak_hour")["median_speed"].mean()

bars = ax2.bar(
    peak_comparison.index,
    peak_comparison.values,
    color=["#E63946", "#457B9D"],
    alpha=0.8,
)
ax2.set_title("高峰 vs 非高峰時段平均車速", fontsize=14, fontweight="bold")
ax2.set_ylabel("平均車速 (mph)")
ax2.set_ylim(0, 80)

# Add value labels on bars
for bar in bars:
    height = bar.get_height()
    ax2.text(
        bar.get_x() + bar.get_width() / 2.0,
        height,
        f"{height:.1f}",
        ha="center",
        va="bottom",
    )

plt.tight_layout()
plt.savefig("monthly_trends_and_peak_comparison.png", dpi=300)
plt.show()
