import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { RefError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { MEMBERSHIP } from "../src/shapes.js";

function tmpRoot(): string {
  return mkdtempSync(join(tmpdir(), "nodes-traversal-"));
}

function setNode(id: string, members: string[]) {
  return makeNode({ id, kind: "set", title: id, facets: { [MEMBERSHIP]: { members } } });
}

/** Registry-free corpus mirroring the fixture cluster: crate ⊃ box ⊃ {tidy, renamed};
 * box lists renamed under its deprecated id; crate lists a dangling note:ghost. */
function seeded(): Corpus {
  const c = new Corpus(tmpRoot());
  c.add(makeNode({ id: "note:renamed", kind: "note", title: "R", deprecatedIds: ["note:old-name"] }));
  c.add(makeNode({ id: "note:tidy", kind: "note", title: "T" }));
  c.add(setNode("set:box", ["note:tidy", "note:old-name"]));
  c.add(setNode("set:crate", ["set:box", "note:ghost"]));
  return c;
}

describe("Corpus — membership traversal", () => {
  it("members skips dangling refs", () => {
    expect(seeded().members("set:crate")).toEqual(["set:box"]);
  });

  it("members resolves deprecated member refs to sorted live ids", () => {
    expect(seeded().members("set:box")).toEqual(["note:renamed", "note:tidy"]);
  });

  it("members of a facet-less node is empty", () => {
    expect(seeded().members("note:tidy")).toEqual([]);
  });

  it("containers resolves a deprecated input ref", () => {
    expect(seeded().containers("note:old-name")).toEqual(["set:box"]);
  });

  it("containers reports direct containers only", () => {
    expect(seeded().containers("set:box")).toEqual(["set:crate"]);
  });

  it("descendants walks nesting transitively and skips dangling", () => {
    expect(seeded().descendants("set:crate")).toEqual(["note:renamed", "note:tidy", "set:box"]);
  });

  it("ancestors walks containers transitively", () => {
    expect(seeded().ancestors("note:renamed")).toEqual(["set:box", "set:crate"]);
  });

  it("cycles terminate and transitive results exclude the start node", () => {
    const c = new Corpus(tmpRoot());
    c.add(setNode("set:loop-a", ["set:loop-b"]));
    c.add(setNode("set:loop-b", ["set:loop-a"]));
    c.add(setNode("set:selfie", ["set:selfie"]));
    expect(c.descendants("set:loop-a")).toEqual(["set:loop-b"]);
    expect(c.ancestors("set:loop-b")).toEqual(["set:loop-a"]);
    expect(c.members("set:selfie")).toEqual(["set:selfie"]);
    expect(c.descendants("set:selfie")).toEqual([]);
    expect(c.ancestors("set:selfie")).toEqual([]);
  });

  it("all four methods reject an unresolvable input ref", () => {
    const c = seeded();
    for (const fn of ["members", "containers", "descendants", "ancestors"] as const) {
      expect(() => c[fn]("note:ghost")).toThrow(RefError);
    }
  });
});
