import { useEffect } from "react";
import { useRegisterEvents, useSigma } from "@react-sigma/core";

interface GraphEventsProps {
  onSelectNode: (nodeId: string | null) => void;
  onHoverNode: (nodeId: string | null) => void;
}

/** Register click and hover events on the graph. */
export function GraphEvents({ onSelectNode, onHoverNode }: GraphEventsProps) {
  const registerEvents = useRegisterEvents();
  const sigma = useSigma();

  useEffect(() => {
    registerEvents({
      clickNode: (event) => {
        onSelectNode(event.node);
      },
      clickStage: () => {
        onSelectNode(null);
      },
      enterNode: (event) => {
        onHoverNode(event.node);
        document.body.style.cursor = "pointer";
      },
      leaveNode: () => {
        onHoverNode(null);
        document.body.style.cursor = "default";
      },
      doubleClickNode: (event) => {
        const attrs = sigma.getGraph().getNodeAttributes(event.node);
        sigma.getCamera().animate(
          { x: attrs.x as number, y: attrs.y as number, ratio: 0.15 },
          { duration: 300 }
        );
      },
    });
  }, [registerEvents, sigma, onSelectNode, onHoverNode]);

  return null;
}
