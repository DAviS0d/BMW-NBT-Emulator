precision mediump float;

varying mediump vec2 vTexCoord;
uniform sampler2D tex0;
uniform sampler2D tex1;
uniform float posY;

void main()
{	
	//cut the top of the texture at specified "posY" position	
	if(posY > vTexCoord.y){
		vec4 texcolor = texture2D(tex0, vTexCoord.xy);	
		vec4 maskcolor = texture2D(tex1, vTexCoord.xy);		
		gl_FragColor = texcolor * maskcolor.r;
	}else{
		gl_FragColor = vec4(0.0,0.0,0.0,0.0);
	}	
}
