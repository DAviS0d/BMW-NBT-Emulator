
precision highp float;

attribute vec4 a_Position;
attribute vec2 a_TextureCoordinate;
attribute vec4 a_Color;

varying mediump vec2 vTexCoord;
varying mediump vec4 vColor;

uniform float    u_PointSize;
uniform mat4     u_transformMatrix;
uniform vec4     u_viewportDimensions;

void main(void)
{
    vec2 pos = a_Position.xy;
    pos.x = pos.x*(u_viewportDimensions.z*2.0) - 1.0;
    pos.y = pos.y*(u_viewportDimensions.w*2.0) - 1.0;
    vColor = a_Color;
    vTexCoord = a_TextureCoordinate;
    vec4 transPos = u_transformMatrix * vec4(pos.xy, 0., 1.);
    transPos /= transPos.w;
    gl_Position = vec4(transPos.xy, a_Position.z, 1.);
    gl_PointSize = 10.;
}
