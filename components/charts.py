import plotly.graph_objs as go


def build_demand_chart(times, demand):
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=times,
            y=demand,
            mode="lines",
            line=dict(color="rgba(0, 212, 255, 0.3)", width=8),
            showlegend=False,
            hoverinfo="skip",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=times,
            y=demand,
            mode="lines",
            name="Demand",
            line=dict(color="#00d4ff", width=3, shape="spline", smoothing=1.3),
            fill="tozeroy",
            fillcolor="rgba(0, 212, 255, 0.1)",
        )
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=40, r=40, t=20, b=40),
        height=350,
        font=dict(family="Inter, sans-serif", color="#e2e8f0"),
        showlegend=False,
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(148, 163, 184, 0.1)",
            zeroline=False,
            tickfont=dict(size=11, color="#64748b"),
        ),
        yaxis=dict(
            title=dict(text="kW", font=dict(size=12, color="#64748b")),
            showgrid=True,
            gridcolor="rgba(148, 163, 184, 0.1)",
            zeroline=False,
            tickfont=dict(size=11, color="#64748b"),
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="rgba(15, 23, 42, 0.9)",
            bordercolor="#00d4ff",
            font=dict(color="#f8fafc"),
        ),
    )

    return fig