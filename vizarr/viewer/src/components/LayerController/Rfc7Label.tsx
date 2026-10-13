import { ContentCopy } from "@mui/icons-material";
import { Divider, IconButton, Link, Popover, Typography } from "@mui/material";
import React from "react";
import type { Rfc7Channel } from "../../utils";

const describe = (c: Rfc7Channel) =>
  c.bio?.entities.map((e) => `${e.role}: ${e.name}${e.external_id ? ` (${e.external_id})` : ""}`).join(" · ") || c.name;

/**
 * Channel (or label) name; with RFC-7 metadata it gets a tooltip and opens a popover with the
 * channel identity (element_names, element_ids UUID) and biological_metadata (CURIEs via bioregistry.io).
 */
export default function Rfc7Label({ label, channel }: { label: string; channel?: Rfc7Channel }) {
  const [anchorEl, setAnchorEl] = React.useState<HTMLElement | null>(null);
  if (!channel) {
    return (
      <Typography variant="caption" noWrap>
        {label}
      </Typography>
    );
  }
  return (
    <>
      <Typography
        variant="caption"
        noWrap
        title={describe(channel)}
        onClick={(e) => setAnchorEl(e.currentTarget)}
        style={{ cursor: "pointer", textDecoration: "underline dotted" }}
      >
        {label}
      </Typography>
      <Popover
        open={Boolean(anchorEl)}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      >
        <div style={{ padding: 8, maxWidth: 340 }}>
          <Typography variant="caption" component="div">
            <b>{channel.name ?? label}</b>
          </Typography>
          <Typography variant="caption" component="div" style={{ fontFamily: "monospace", fontSize: "0.65em" }}>
            {channel.id}
            <IconButton
              size="small"
              title="Copy channel id"
              onClick={() => navigator.clipboard?.writeText(channel.id)}
              style={{ padding: 2 }}
            >
              <ContentCopy style={{ fontSize: 12 }} />
            </IconButton>
          </Typography>
          {channel.bio && <Divider style={{ margin: "4px 0" }} />}
          {channel.bio?.entities.map((e) => (
            <Typography key={`${e.role}-${e.name}`} variant="caption" component="div">
              <b>{e.role}</b>: {e.name}{" "}
              {e.external_id && (
                <Link href={`https://bioregistry.io/${e.external_id}`} target="_blank" rel="noopener noreferrer">
                  {e.external_id}
                </Link>
              )}
            </Typography>
          ))}
          {channel.bio?.relationships?.map((r) => (
            <Typography key={`${r.subject}-${r.relation}-${r.object}`} variant="caption" component="div">
              {r.subject} <i>{r.relation}</i> {r.object}
            </Typography>
          ))}
        </div>
      </Popover>
    </>
  );
}
